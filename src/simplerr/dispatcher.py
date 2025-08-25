from __future__ import annotations

import logging
import os
import typing as t
from datetime import timedelta
from pathlib import Path

import sys
from werkzeug.datastructures import ImmutableDict
from werkzeug.exceptions import HTTPException, InternalServerError, BadRequestKeyError, NotFound
from werkzeug.routing import RoutingException, RequestRedirect, MapAdapter, Map
from werkzeug.utils import cached_property
from werkzeug.wsgi import get_host

from .config import Config
from .ctx import _AppCtxGlobals, AppContext, RequestContext
from .events import WebEvents
from .globals import request, request_ctx
from .helpers import get_debug_flag, get_root_path
from .json.provider import JSONProvider, DefaultJSONProvider
from .logging import create_logger
from .session import SecureCookieSessionInterface
from .typing import ResponseReturnValue
from .web import web
from .wrappers import Request, Response


class SiteError(Exception):
    """Base class for exceptions in this module."""

    pass


class SiteNoteFoundError(SiteError):
    """Exception raised for errors in the site path

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, site, message):
        self.site = site
        self.message = message
        super().__init__(message)


# WSGI Server
class wsgi(object):
    request_class = Request

    response_class = Response

    config_class = Config

    session_interface = SecureCookieSessionInterface()

    app_ctx_globals_class = _AppCtxGlobals

    json_provider_class: type[JSONProvider] = DefaultJSONProvider

    url_map_class = Map

    default_config = ImmutableDict({
        'DEBUG': None,
        'TESTING': False,
        'PROPAGATE_EXCEPTIONS': None,
        'SECRET_KEY': None,
        'SECRET_KEY_FALLBACKS': None,
        'PERMANENT_SESSION_LIFETIME': timedelta(days=31),
        'SERVER_NAME': None,
        'APPLICATION_ROOT': '/',
        'SESSION_COOKIE_NAME': 'session',
        'SESSION_COOKIE_DOMAIN': None,
        'SESSION_COOKIE_PATH': None,
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SECURE': False,
        'SESSION_COOKIE_SAMESITE': None,
        'SESSION_REFRESH_EACH_REQUEST': True,
    })

    def __init__(
            self,
            import_name: str,
            site: str | os.PathLike[str] | None = None,
            root_path: str | None = None,
            host_matching: bool = False,
            subdomain_matching: bool = False,
            extension=".py",
    ):

        self.import_name = import_name
        self.debug = False

        if root_path is None:
            root_path = get_root_path(self.import_name)

        self.root_path = root_path
        self.site = site
        self.extension = extension
        self.json = self.json_provider_class(self)
        self.url_map = self.url_map_class(host_matching=host_matching)
        self.subdomain_matching = subdomain_matching

        self.cwd = self._resolve_cwd()

        # Add Relevent Web Events
        # NOTE: Events created at this level should fire static events that
        # are fired on every request and will share application data, all other
        # events should be reset between views. Make sure to not use the global
        # object unless you want the event called at every view.
        self.global_events = WebEvents()

        # Add CWD to search path, this is where project modules will be located
        self._setup_path()
        self.config = self.make_config()

    @cached_property
    def name(self) -> str:
        if self.import_name == "__main__":
            fn: str | None = getattr(sys.modules["__main__"], "__file__", None)
            if fn is None:
                return "__main__"
            return os.path.splitext(os.path.basename(fn))[0]
        return self.import_name

    @property
    def site(self) -> str:
        if self._site is not None:
            return os.path.join(self.root_path, self._site)
        else:
            return os.path.join(self.root_path, "website")

    @site.setter
    def site(self, value: str | os.PathLike[str] | None) -> None:
        if value is not None:
            value = os.fspath(value).rstrip(os.sep)
        self._site = value

    def app_context(self) -> AppContext:
        return AppContext(self)

    def request_context(self, environ: dict[str, t.Any]) -> RequestContext:
        return RequestContext(self, environ)

    def create_url_adapter(self, request: Request | None = None) -> MapAdapter | None:
        if request is not None:
            if (trusted_hosts := self.config.get("TRUSTED_HOSTS", None)) is not None:
                request.trusted_hosts = trusted_hosts
            request.host = get_host(request.environ, request.trusted_hosts)
            subdomain = None
            server_name = self.config["SERVER_NAME"]

            if self.url_map.host_matching:
                server_name = None
            elif not self.subdomain_matching:
                subdomain = self.url_map.default_subdomain or ""

            return self.url_map.bind_to_environ(
                request.environ, server_name=server_name, subdomain=subdomain
            )
        if self.config.get('SERVER_NAME', None) is not None:
            return self.url_map.bind(
                self.config.get('SERVER_NAME'),
                script_name=self.config.get('APPLICATION_ROOT', '/'),
                url_scheme=self.config.get('PREFERRED_URL_SCHEME', 'http')
            )

        return None

    @cached_property
    def logger(self) -> logging.Logger:
        return create_logger(self)

    def log_exception(self, exc_info) -> None:
        self.logger.error(
            f'Exception on {request.path} [{request.method}]', exc_info=exc_info
        )

    def make_config(self) -> Config:
        """Creates a new config object with the default values merged in."""
        defaults = dict(self.default_config)
        defaults['DEBUG'] = get_debug_flag()
        return self.config_class(defaults)

    def make_default_options_response(self) -> Response:
        """Creates a default response for OPTIONS requests."""
        rv = self.response_class()
        return rv

    def do_teardown_request(self, request: Request, error: t.Optional[BaseException] = None):
        for fn in reversed(self.global_events.teardown_request):
            rv = fn(request, error)
            if rv is not None:
                error = rv

    def should_ignore_error(self, error: t.Optional[BaseException] = None) -> bool:
        return False

    def full_dispatch_request(self) -> Response:
        self._got_first_request = True

        try:
            rv = self.preprocess_request()
            if rv is None:
                rv = self.dispatch_request()
        except Exception as e:
            rv = self.handle_user_exception(e)
        return self.finalize_request(rv)

    def preprocess_request(self) -> t.Optional[Response]:

        for fn in self.global_events.pre_request:
            rv = fn(request)
            if rv is not None:
                return rv

        return None

    def handle_http_exeption(self, e) -> HTTPException:
        if e.code is None:
            return e

        if isinstance(e, RoutingException):
            return e

        return e

    def handle_exception(self, e: BaseException) -> Response:
        exc_info = sys.exc_info()
        propogate = self.config.get("PROPAGATE_EXCEPTIONS")

        if propogate is None:
            propogate = self.debug
        if propogate:
            if exc_info[1] is e:
                raise
            raise e

        self.log_exception(exc_info)
        server_error = InternalServerError(original_exception=e)

        if isinstance(e, OSError):
            server_error = NotFound()

        return self.finalize_request(server_error, from_error_handler=True)

    def handle_user_exception(self, e) -> HTTPException:
        if isinstance(e, BadRequestKeyError) and self.debug:
            e.show_exception = True
        if isinstance(e, HTTPException):
            return self.handle_http_exeption(e)

        return e

    def finalize_request(self, rv: t.Union[ResponseReturnValue, HTTPException],
                         from_error_handler: bool = False) -> Response:
        response = web.make_response(request=request, rv=rv)
        try:
            response = self.process_response(response)
        except Exception:
            if not from_error_handler:
                raise
            self.logger.error(f"Request finalizing failed with an error while handling an error")

        return response

    def process_response(self, response: Response) -> Response:
        ctx = request_ctx._get_current_object() # type: ignore[attr-defined]


        for fn in reversed(self.global_events.post_request):
            rv = fn(ctx.request, response)
            if rv is not None:
                response = rv

        if not self.session_interface.is_null_session(ctx.session):
            self.session_interface.save_session(self, ctx.session, response)

        return response

    def raise_routing_exception(self, request: Request):
        if (
                not self.debug
                or not isinstance(request.routing_exception, RequestRedirect)
                or request.routing_exception.code in {307, 308}
                or request.method in {"GET", "HEAD", "OPTIONS"}
        ):
            raise request.routing_exception

        return None

    def dispatch_request(self) -> ResponseReturnValue:
        req = request_ctx.request
        if req.routing_exception is not None:
            self.raise_routing_exception(req)

        rule = req.url_rule

        if (
                getattr(rule, "provide_automatic_options", False)
                and req.method == "OPTIONS"
        ):
            return self.make_default_options_response()

        view_args: dict[str, t.Any] = request.view_args
        return req.match.fn(req, **view_args)

    def _resolve_cwd(self) -> Path:
        path_site = Path(self.site)
        path_with_cwd = Path.cwd() / path_site

        if path_site.exists():
            return path_site

        if path_with_cwd.exists():
            return path_with_cwd

        raise SiteNoteFoundError(self.site, "Could not access folder")

    def _setup_path(self):
        sys.path.append(self.cwd.absolute().__str__())

    def wsgi_app(self, environ, start_response):
        """This methods provides the basic call signature required by WSGI"""
        ctx = self.request_context(environ)
        error: t.Optional[BaseException] = None
        try:
            try:
                ctx.push()
                response = self.full_dispatch_request()
            except Exception as e:
                error = e
                response = self.handle_exception(e)
            except:
                error = sys.exc_info()[1]
                raise
            return response(environ, start_response)
        finally:
            if error is not None and self.should_ignore_error(error):
                error = None
            ctx.pop(error)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

    def serve(self,
              host: t.Optional[str] = None,
              port: t.Optional[int] = None,
              debug: t.Optional[bool] = None,
              **options: t.Any
              ):
        """Start a new development server."""
        if debug is not None:
            self.debug = bool(debug)

        server_name = self.config.get("SERVER_NAME")
        sn_host = sn_port = None

        if server_name:
            sn_host, _, sn_port = server_name.partition(":")

        if not host:
            if sn_host:
                host = sn_host
            else:
                host = "127.0.0.1"

        if port or port == 0:
            port = int(port)
        elif sn_port:
            port = int(sn_port)
        else:
            port = 3200

        options.setdefault("use_reloader", self.debug)
        options.setdefault("use_debugger", self.debug)
        options.setdefault("threaded", True)

        from werkzeug.serving import run_simple

        try:
            run_simple(t.cast(str, host), port, self, **options)
        finally:
            self._got_first_request = False
