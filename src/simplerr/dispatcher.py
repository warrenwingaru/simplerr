import logging

import typing as t

from werkzeug.routing import RoutingException, RequestRedirect
from werkzeug.serving import run_simple
from werkzeug.exceptions import NotFound, HTTPException, InternalServerError, BadRequestKeyError
from werkzeug.debug import DebuggedApplication
from pathlib import Path
from inspect import iscoroutinefunction

from .events import WebEvents
from .web import web
import sys

from .script import script
from .session import FileSystemSessionStore
from .wrappers import Request, Response

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


class dispatcher(object):
    def __init__(self, cwd, global_events: WebEvents, extension=".py"):
        self.cwd = cwd
        self.global_events = global_events
        self.extension = extension


    def __call__(self, environ, start_response):
        """This methods provides the basic call signature required by WSGI"""
        error: t.Optional[BaseException] = None
        try:
            request = Request(environ)
            try:
                response = self.full_dispatch_request(environ)
            except Exception as e:
                error = e
                response = self.handle_exception(request, e)
            except:
                error = sys.exc_info()[1]
                raise
            return response(environ, start_response)
        finally:
            if error is not None and  self.should_ignore_error(error):
                error = None
            self.do_teardown_request(error)


    def do_teardown_request(self, error: t.Optional[BaseException] = None):
        for fn in reversed(self.global_events.teardown_request):
            rv = fn(error)
            if rv is not None:
                error = rv

    def should_ignore_error(self, error: t.Optional[BaseException] = None) -> bool:
        return False

        # response, exc = self.dispatch_request(request, environ)
        #
        # try:
        #     return response(environ, start_response)
        # finally:
        #     # Fire post response events
        #     request.view_events.fire_post_response(request, response, exc)
        #     self.global_events.fire_post_response(request, response, exc)

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

    def handle_exception(self, request, e) -> Response:
        server_error = InternalServerError(str(e))
        return self.finalize_request(request, server_error, from_error_handler=True)

    def handle_user_exception(self, e) -> HTTPException:
        if isinstance(e, BadRequestKeyError) and self.debug:
            e.show_exception = True
        if isinstance(e, HTTPException):
            return self.handle_http_exeption(e)

        return e

    def finalize_request(self, request: Request, rv: Response, from_error_handler: bool =False) -> Response:
        response = web.make_response(request=request, rv=rv)
        try:
            response = self.process_response(request,response)
        except Exception as e:
            if not from_error_handler:
                raise
            logger.error(f"Request finalizing failed with an error while handling an error")

        return response

    def process_response(self, request: Request,response: Response) -> Response:

        for fn in reversed(self.global_events.post_request):
            rv = fn(request,response)
            if rv is not None:
                response = rv

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

    def dispatch_request(self, request: Request):

        web.restore_presets()

        # Get view script and view module
        sc = script(self.cwd, request.path, extension=self.extension)
        sc.get_module()

        match = web.match(request)
        request.cwd = self.cwd

        if request.routing_exception is not None:
            self.raise_routing_exception(request)

        view_args: dict[str, t.Any] = request.view_args
        return match.fn(request, **view_args)


# WSGI Server
class wsgi(object):
    def __init__(
            self,
            site,
            extension=".py"
    ):

        self.site = site
        self.extension = extension

        # TODO: Need to update interface to handle these
        self.session_store = FileSystemSessionStore()

        self.cwd = self._resolve_cwd()

        # Add Relevent Web Events
        # NOTE: Events created at this level should fire static events that
        # are fired on every request and will share application data, all other
        # events should be reset between views. Make sure to not use the global
        # object unless you want the event called at every view.
        self.global_events = WebEvents()

        self._setup_events()

        # Add CWD to search path, this is where project modules will be located
        self._setup_path()

    def _resolve_cwd(self) -> Path:
        path_site = Path(self.site)
        path_with_cwd = Path.cwd() / path_site

        if path_site.exists():
            return path_site

        if path_with_cwd.exists():
            return path_with_cwd

        raise SiteNoteFoundError(self.site, "Could not access folder")

    def _setup_events(self):
        # Add some key events
        self.global_events.on_pre_response(self.session_store.pre_response)
        self.global_events.on_post_response(self.session_store.post_response)

    def _setup_path(self):
        sys.path.append(self.cwd.absolute().__str__())


    def make_app(self):
        self.wsgi_app = dispatcher(self.cwd, self.global_events, self.extension)
        return self.wsgi_app

    def wsgi_app(self, environ, start_response):
        return dispatcher(self.cwd, self.global_events, self.extension)(environ, start_response)

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
