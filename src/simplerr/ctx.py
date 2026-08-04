from __future__ import annotations

import contextvars
import typing as t

from .globals import _cv_app
from .helpers import _CollectErrors

if t.TYPE_CHECKING:
    import typing_extensions as te
    from _typeshed.wsgi import WSGIEnvironment

    from .dispatcher import wsgi
    from .wrappers import Request
    from .session import SessionSignalMixin

# a singleton sentinel value for parameter defaults
_sentinel = object()


class _AppCtxGlobals:
    def __getattr__(self, name: str) -> t.Any:
        try:
            return self.__dict__[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: t.Any) -> None:
        self.__dict__[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self.__dict__[name]
        except KeyError:
            raise AttributeError(name) from None

    def get(self, name: str, default: t.Optional[t.Any] = None) -> t.Any:
        return self.__dict__.get(name, default)

    def pop(self, name: str, default: t.Optional[t.Any] = None) -> t.Any:
        if default is _sentinel:
            return self.__dict__.pop(name)
        return self.__dict__.pop(name, default)

    def setdefault(self, name: str, default: t.Optional[t.Any] = None):
        return self.__dict__.setdefault(name, default)

    def __contains__(self, item: str) -> bool:
        return item in self.__dict__

    def __iter__(self) -> t.Iterator[str]:
        return iter(self.__dict__)

    def __repr__(self) -> str:
        ctx = _cv_app.get(None)
        if ctx is not None:
            return f"<simplerr.g of '{ctx.app.name}>"
        return object.__repr__(self)

class AppContext:

    def __init__(
            self,
            app: wsgi,
            *,
            request: t.Optional[Request] = None,
            session: t.Optional[SessionSignalMixin] = None,
    ):
        self.app = app
        self.g: _AppCtxGlobals = app.app_ctx_global_class()

        self._request = request
        self._session = session

        self._cv_token: t.Optional[contextvars.Token[AppContext]] = None
        self._push_count: int = 0

    @classmethod
    def from_environ(cls, app: wsgi, environ: WSGIEnvironment) -> te.Self:
        request = app.request_class(environ)
        return cls(app, request=request)

    @property
    def has_request(self) -> bool:
        return self._request is not None

    @property
    def request(self) -> Request:
        if self._request is None:
            raise RuntimeError("There is no request in this context.")
        return self._request

    def _get_session(self) -> SessionSignalMixin:
        if self._request is None:
            raise RuntimeError("There is no request in this context.")

        if self._session is None:
            si = self.app.session_interface
            self._session = si.open_session(self.app, self.request)

            if self._session is None:
                self._session = si.make_null_session(self.app)

        return self._session

    @property
    def session(self) -> SessionSignalMixin:
        session = self._get_session()
        session.accessed = True
        return session

    def push(self):
        self._push_count += 1

        if self._cv_token is not None:
            return

        if self._request is not None:
            self._get_session()

            self.app.match(self._request)

        self._cv_token = _cv_app.set(self)

    def pop(self, exc: t.Optional[BaseException] = None):
        if self._cv_token is None:
            raise RuntimeError(f"Cannot pop this context ({self!r}, is not pushed")

        ctx = _cv_app.get(None)

        if ctx is None or self._cv_token is None:
            raise RuntimeError(f"Cannot pop this context ({self!r}, there is no active context")

        if ctx is not self:
            raise RuntimeError(
                f"Cannot pop this context ({self!r}, it is not the active context"
                f" context ({ctx!r})."
            )

        self._push_count -= 1

        if self._push_count > 0:
            return

        collect_errors = _CollectErrors()

        if self._request is not None:
            with collect_errors:
                self.app.do_teardown_request(self, exc)

            with collect_errors:
                self.request.close()

        _cv_app.reset(self._cv_token)
        self._cv_token = None

        collect_errors.raise_any("Errors occurred during teardown")


    def __enter__(self):
        self.push()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.pop(exc_value)

    def __repr__(self):
        return f"<{type(self).__name__} {id(self)} of {self.app.name}>"
