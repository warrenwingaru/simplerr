from __future__ import annotations

import typing as t
from contextvars import ContextVar

from werkzeug.local import LocalProxy

if t.TYPE_CHECKING:
    from .dispatcher import wsgi
    from .ctx import _AppCtxGlobals
    from .ctx import AppContext
    from .session import SessionSignalMixin
    from .wrappers import Request

    T = t.TypeVar("T", covariant=True)


    class ProxyMixin(t.Protocol[T]):
        def _get_current_object(self) -> T: ...


    class SimplerrProxy(ProxyMixin[wsgi], wsgi): ...


    class AppContextProxy(ProxyMixin[AppContext], AppContext): ...


    class _AppCtxGlobalsProxy(ProxyMixin[_AppCtxGlobals], _AppCtxGlobals): ...


    class RequestProxy(ProxyMixin[Request], Request): ...


    class SessionMixinProxy(ProxyMixin[SessionSignalMixin], SessionSignalMixin): ...

_cv_app: ContextVar[AppContext] = ContextVar("simplerr.app_ctx")
_no_app_msg = """\
    Working outside of application context.
"""
app_ctx: AppContextProxy = LocalProxy(  # type: ignore[assignment]
    _cv_app, unbound_message=_no_app_msg
)
current_app: SimplerrProxy = LocalProxy(  # type: ignore[assignment]
    _cv_app, "app", unbound_message=_no_app_msg
)
g: _AppCtxGlobalsProxy = LocalProxy(  # type: ignore[assignment]
    _cv_app, "g", unbound_message=_no_app_msg
)

_no_req_msg = """\
    Working outside of request context.
"""
request: RequestProxy = LocalProxy( # type: ignore[assignment]
    _cv_app, "request", unbound_message=_no_req_msg
)
session: SessionMixinProxy = LocalProxy( # type: ignore[assignment]
    _cv_app, "session", unbound_message=_no_req_msg
)