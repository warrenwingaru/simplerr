from __future__ import annotations
import logging
import sys
import typing as t
from pathlib import Path

from werkzeug.exceptions import HTTPException, InternalServerError, BadRequestKeyError, NotFound, MethodNotAllowed
from werkzeug.routing import RoutingException, RequestRedirect

from .events import WebEvents
from .script import script
from .session import SecureCookieSessionInterface
from .typing import ResponseReturnValue
from .web import web
from .wrappers import Request, Response

if t.TYPE_CHECKING:
    from .testing import SimplerrClient
    from _typeshed.wsgi import WSGIEnvironment, StartResponse

logger = logging.getLogger(__name__)


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


class Simplerr(object):
    request_class: type[Request] = Request

    response_class: type[Response] = Response

    session_interface = SecureCookieSessionInterface()

    test_client_class: type[SimplerrClient] = None

    def __init__(
            self,
            site,
            extension=".py"
    ):
        self.config = {
            'DEBUG': None,
            'TESTING': False,
            'SECRET_KEY': None,
            'SECRET_KEY_FALLBACKS': None,
            'SESSION_COOKIE_NAME': 'session',
            'SESSION_COOKIE_DOMAIN': None,
            'SESSION_COOKIE_PATH': None,
            'SESSION_COOKIE_HTTPONLY': True,
            'SESSION_COOKIE_SECURE': False,
            'SESSION_COOKIE_SAMESITE': None,
            'SESSION_REFRESH_EACH_REQUEST': True,

        }

        self.testing = False
        self.debug = False
        self.site = site
        self.extension = extension

        self.cwd = self._resolve_cwd()

        # Add Relevent Web Events
        # NOTE: Events created at this level should fire static events that
        # are fired on every request and will share application data, all other
        # events should be reset between views. Make sure to not use the global
        # object unless you want the event called at every view.
        self.global_events = WebEvents()

        # Add CWD to search path, this is where project modules will be located
        self._setup_path()

    def test_client(self, *args, **kwargs) -> SimplerrClient:
        cls = self.test_client_class
        if cls is None:
            from .testing import SimplerrClient as cls
        return cls(self, self.response_class, *args, **kwargs)

    def make_default_options_response(self) -> Response:
        """Creates a default response for OPTIONS requests."""
        rv = self.response_class()
        return rv

    def do_teardown_request(self, request: Request, error: t.Optional[BaseException] = None):
        for fn in reversed(self.global_events.teardown_request):
            rv = fn(request, error)
            if rv is not None:
                error = rv

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

    def full_dispatch_request(self, request) -> Response:
        self._got_first_request = True

        try:
            rv = self.preprocess_request(request)
            if rv is None:
                rv = self.dispatch_request(request)
        except Exception as e:
            rv = self.handle_user_exception(e)
        return self.finalize_request(request, rv)

    def preprocess_request(self, request: Request) -> t.Optional[Response]:

        try:
            if request.session is None:
                session_interface = self.session_interface
                request.session = session_interface.open_session(self, request)

                if request.session is None:
                    request.session = session_interface.make_null_session(self)
        except AttributeError:
            pass


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

    def handle_exception(self, request, e: BaseException) -> Response:
        exc_info = sys.exc_info()
        propogate = None

        if propogate is None:
            propogate = self.debug
        if propogate:
            if exc_info[1] is e:
                raise
            raise e

        server_error = InternalServerError(original_exception=e)

        if isinstance(e, OSError):
            server_error = NotFound()

        return self.finalize_request(request, server_error, from_error_handler=True)

    def handle_user_exception(self, e) -> HTTPException:
        if isinstance(e, BadRequestKeyError) and self.debug:
            e.show_exception = True
        if isinstance(e, HTTPException):
            return self.handle_http_exeption(e)

        return e

    def finalize_request(self, request: Request, rv: t.Union[ResponseReturnValue, HTTPException] , from_error_handler: bool = False) -> Response:
        response = web.make_response(request=request, rv=rv)
        try:
            response = self.process_response(request, response)
        except Exception as e:
            if not from_error_handler:
                raise
            logger.error(f"Request finalizing failed with an error while handling an error")

        return response

    def process_response(self, request: Request, response: Response) -> Response:

        for fn in reversed(self.global_events.post_request):
            rv = fn(request, response)
            if rv is not None:
                response = rv


        if not self.session_interface.is_null_session(request.session):
            self.session_interface.save_session(self, request.session, response)

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

    def dispatch_request(self, request: Request) -> ResponseReturnValue:
        if request.routing_exception is not None:
            self.raise_routing_exception(request)

        if request.method == "OPTIONS":
            return self.make_default_options_response()

        view_args: dict[str, t.Any] = request.view_args
        return request.match.fn(request, **view_args)

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

    def wsgi_app(self, environ: WSGIEnvironment, start_response: StartResponse):
        """This methods provides the basic call signature required by WSGI"""
        error: t.Optional[BaseException] = None
        request = self.request_class(environ)
        self.match(request)
        try:
            try:
                response = self.full_dispatch_request(request)
            except Exception as e:
                error = e
                response = self.handle_exception(request, e)
            except:
                error = sys.exc_info()[1]
                raise
            return response(environ, start_response)
        finally:
            if error is not None and self.should_ignore_error(error):
                error = None
            self.do_teardown_request(request, error)

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse):
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

        server_name = None
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


# WSGI Server
def wsgi(*args, **kwargs):
    return Simplerr(*args, **kwargs)