# fleshed out from flask https://github.com/pallets/flask/blob/main/src/flask/ctx.py
from __future__ import annotations

import contextvars
import typing as t

import sys
from werkzeug.exceptions import HTTPException

from .web import web
from .globals import _cv_app
from .globals import _cv_request
from .script import script

if t.TYPE_CHECKING:
    from _typeshed.wsgi import WSGIEnvironment

    from .dispatcher import wsgi
    from .session import SessionSignalMixin
    from .wrappers import Request

_sentinel = object()


class _AppCtxGlobals:
    """A plain object. Used as a namespace for storing data during an application context."""

    def __getattr__(self, name: str):
        try:
            return self.__dict__[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: t.Any):
        self.__dict__[name] = value

    def __delattr__(self, name: str):
        try:
            del self.__dict__[name]
        except KeyError:
            raise AttributeError(name) from None

    def get(self, name: str, default: t.Any | None = None) -> t.Any:
        return self.__dict__.get(name, default)

    def pop(self, name: str, default: t.Any | None = None) -> t.Any:
        if default is _sentinel:
            return self.__dict__.pop(name)
        else:
            return self.__dict__.pop(name, default)

    def setdefault(self, name: str, default: t.Any = None) -> t.Any:
        return self.__dict__.setdefault(name, default)

    def __contains__(self, item: str) -> bool:
        return item in self.__dict__

    def __iter__(self):
        return iter(self.__dict__)

    def __repr__(self):
        ctx = _cv_app.get(None)
        if ctx is not None:
            return f"<simplerr.g of '{ctx.app.name}'>"
        return object.__repr__(self)


if t.TYPE_CHECKING:
    from .dispatcher import wsgi


class AppContext:
    """The app context contains application-specific information."""

    def __init__(self, app: wsgi):
        self.app = app
        self.g = self.app.app_ctx_globals_class()
        self._cv_tokens: list[contextvars.Token[AppContext]] = []

    def push(self) -> None:
        self._cv_tokens.append(_cv_app.set(self))

    def pop(self, exc: BaseException | None = _sentinel) -> None:
        try:
            if len(self._cv_tokens) == 1:
                if exc is _sentinel:
                    exc = sys.exc_info()[1]
                # don't really think we need.
                # self.app.do_teardown_appcontext(exc)
        finally:
            ctx = _cv_app.get()
            _cv_app.reset(self._cv_tokens.pop())

        if ctx is not self:
            raise AssertionError(f"Popped wrong app context. ({ctx!r} instead of {self!r})")

    def __enter__(self) -> AppContext:
        self.push()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pop(exc_val)


class RequestContext:
    def __init__(
            self,
            app: wsgi,
            environ: WSGIEnvironment,
            request: Request | None = None,
            session: SessionSignalMixin | None = None,
    ):
        self.app = app
        if request is None:
            request = app.request_class(environ)
            request.json_module = app.json
        self.request = request
        self.url_adapter = None
        try:
            self.url_adapter = app.create_url_adapter(self.request)
        except HTTPException as e:
            self.request.routing_exception = e
        self.session = session

        self._cv_tokens: list[
            tuple[contextvars.Token[RequestContext], AppContext | None]
        ] = []

    def match_request(self):
        try:
            web.restore_presets()
            # Get view script and view module
            sc = script(self.app.cwd, self.request.path, extension=self.app.extension)
            sc.get_module()

            self.request.url_rule, self.request.view_args, self.request.match = web.match_request(self.request)
            self.request.environ['simplerr.url_rule'] = self.request.url_rule
        except HTTPException as e:
            self.request.routing_exception = e
        finally:
            self.request.cwd = self.app.cwd

    def push(self) -> None:
        app_ctx = _cv_app.get(None)

        if app_ctx is None or app_ctx.app is not self.app:
            app_ctx = self.app.app_context()
            app_ctx.push()
        else:
            app_ctx = None

        self._cv_tokens.append((_cv_request.set(self), app_ctx))

        if self.session is None:
            session_interface = self.app.session_interface
            self.session = session_interface.open_session(self.app, self.request)

            if self.session is None:
                self.session = session_interface.make_null_session(self.app)

        self.request.session = self.session

        if self.url_adapter is not None:
            self.match_request()

    def pop(self, exc: BaseException | None = _sentinel) -> None:
        clear_request = len(self._cv_tokens) == 1

        try:
            if clear_request:
                if exc is _sentinel:
                    exc = sys.exc_info()[1]
                self.app.do_teardown_request(self.request, exc)

                request_close = getattr(self.request, "close", None)
                if request_close is not None:
                    request_close()
        finally:
            ctx = _cv_request.get()
            token, app_ctx = self._cv_tokens.pop()
            _cv_request.reset(token)

            if clear_request:
                ctx.request.environ['werkzeug.request'] = None

            if app_ctx is not None:
                app_ctx.pop(exc)

            if ctx is not self:
                raise AssertionError(f"Popped wrong request context. ({ctx!r} instead of {self!r})")

    def __enter__(self) -> RequestContext:
        self.push()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.pop(exc_val)

    def __repr__(self):
        return (
            f"<{type(self).__name__} {self.request.url!r}"
            f" [{self.request.method}] of {self.app.name}>"

        )
