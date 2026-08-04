from __future__ import annotations

import logging
import os.path
import sys
import typing as t
from datetime import timedelta
from functools import cached_property
from pathlib import Path
from inspect import iscoroutinefunction
from types import TracebackType

from werkzeug.datastructures import ImmutableDict
from werkzeug.exceptions import HTTPException, InternalServerError, BadRequestKeyError, NotFound
from werkzeug.routing import RoutingException, RequestRedirect

from .config import Config
from .ctx import _AppCtxGlobals, AppContext
from .events import WebEvents
from .helpers import get_debug_flag, _CollectErrors
from .logging import create_logger
from .script import script
from .session import SecureCookieSessionInterface
from .typing import ResponseReturnValue
from .web import web
from .wrappers import Request, Response

if t.TYPE_CHECKING:
    from _typeshed.wsgi import WSGIEnvironment

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

    app_ctx_global_class = _AppCtxGlobals

    request_class = Request

    response_class = Response

    config_class = Config

    session_interface = SecureCookieSessionInterface()

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
            site,
            import_name: str = __name__,
            extension=".py"
    ):

        self.debug = False
        self.site = site
        self.extension = extension
        self.import_name = import_name

        self.cwd = self._resolve_cwd()
        self.extensions: dict[str, t.Any] = {}

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
            fn: t.Optional[str] = getattr(sys.modules["__main__"], "__file__", None)
            if fn is None:
                return "__main__"
            return os.path.splitext(os.path.basename(fn))[0]
        return self.import_name

    @cached_property
    def logger(self) -> logging.Logger:
        return create_logger(self)

    def log_exception(
            self,
            ctx: AppContext,
            exc_info: tuple[type, BaseException, TracebackType] | tuple[None, None, None],
    ):
        self.logger.error(
            f"Exception on {ctx.request.path} [{ctx.request.method}]", exc_info=exc_info
        )

    def make_config(self) -> Config:
        """Creates a new config object with the default values merged in."""
        defaults = dict(self.default_config)
        defaults['DEBUG'] = get_debug_flag()
        return self.config_class(defaults)

    def ensure_sync(self, func: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
        if iscoroutinefunction(func):
            return self.async_to_sync(func)
        return func

    def async_to_sync(self, func: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
        try:
            from asgiref.sync import async_to_sync as asgiref_async_to_sync
        except ImportError:
            raise RuntimeError(
                "Install simplerr with the 'async' extra in order to use async views"
            ) from None
        return asgiref_async_to_sync(func)

    def app_context(self) -> AppContext:
        return AppContext(self)

    def request_context(self, environ: WSGIEnvironment) -> AppContext:
        return AppContext.from_environ(self, environ)

    def make_default_options_response(self) -> Response:
        """Creates a default response for OPTIONS requests."""
        rv = self.response_class()
        return rv

    def do_teardown_request(self, ctx: AppContext, error: t.Optional[BaseException] = None):
        collect_errors = _CollectErrors()

        for fn in reversed(self.global_events.teardown_request):
            with collect_errors:
                rv = self.ensure_sync(fn)(ctx.request, error)
                if rv is not None:
                    error = rv

        collect_errors.raise_any("Errors during request teardown")

    def match(self, request: Request):
        try:
            web.restore_presets()
            # Get view script and view module
            sc = script(self.cwd, request.path, extension=self.extension)
            sc.get_module()

            request.url_rule, request.view_args, request.match = web.match_request(request)
            request.environ['simplerr.url_rule'] = request.url_rule
        except HTTPException as e:
            request.routing_exception = e
        finally:
            request.cwd = self.cwd

    def should_ignore_error(self, error: t.Optional[BaseException] = None) -> bool:
        return False

    def full_dispatch_request(self, ctx: AppContext) -> Response:
        self._got_first_request = True

        try:
            rv = self.preprocess_request(ctx)
            if rv is None:
                rv = self.dispatch_request(ctx)
        except Exception as e:
            rv = self.handle_user_exception(e)
        return self.finalize_request(ctx, rv)

    def preprocess_request(self, ctx: AppContext) -> t.Optional[Response]:
        request = ctx.request

        for fn in self.global_events.pre_request:
            rv = self.ensure_sync(fn)(request)
            if rv is not None:
                return rv

        return None

    def handle_http_exeption(self, e) -> HTTPException:
        if e.code is None:
            return e

        if isinstance(e, RoutingException):
            return e

        return e

    def handle_exception(self, ctx: AppContext, e: BaseException) -> Response:
        exc_info = sys.exc_info()
        propogate = self.config.get("PROPAGATE_EXCEPTIONS")

        if propogate is None:
            propogate = self.debug
        if propogate:
            if exc_info[1] is e:
                raise
            raise e

        self.log_exception(ctx, exc_info)
        server_error = InternalServerError(original_exception=e)

        if isinstance(e, OSError):
            server_error = NotFound()
        return self.finalize_request(ctx, server_error, from_error_handler=True)

    def handle_user_exception(self, e) -> HTTPException:
        if isinstance(e, BadRequestKeyError) and self.debug:
            e.show_exception = True
        if isinstance(e, HTTPException):
            return self.handle_http_exeption(e)

        return e

    def finalize_request(self, ctx: AppContext, rv: t.Union[ResponseReturnValue, HTTPException] , from_error_handler: bool = False) -> Response:
        request = ctx.request
        response = web.make_response(request=request, rv=rv)
        try:
            response = self.process_response(ctx, response)
        except Exception as e:
            if not from_error_handler:
                raise
            self.logger.error(f"Request finalizing failed with an error while handling an error")

        return response

    def process_response(self, ctx: AppContext, response: Response) -> Response:

        for fn in reversed(self.global_events.post_request):
            rv = self.ensure_sync(fn)(ctx.request, response)
            if rv is not None:
                response = rv

        if not self.session_interface.is_null_session(ctx._get_session()):
            self.session_interface.save_session(self, ctx._get_session(), response)

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

    def dispatch_request(self, ctx: AppContext) -> ResponseReturnValue:
        request = ctx.request

        if request.routing_exception is not None:
            self.raise_routing_exception(request)

        if request.method == "OPTIONS":
            return self.make_default_options_response()

        view_args: dict[str, t.Any] = request.view_args
        return self.ensure_sync(request.match.fn)(request, **view_args)

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
                response = self.full_dispatch_request(ctx)
            except Exception as e:
                error = e
                response = self.handle_exception(ctx, e)
            except:
                error = sys.exc_info()[1]
                raise
            return response(environ, start_response)
        finally:
            if "werkzeug.debug.preserve_context" in environ:
                environ["werkzeug.debug.preserve_context"](ctx)

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
