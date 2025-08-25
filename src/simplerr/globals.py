from __future__ import annotations

import typing as t
from contextvars import ContextVar

from werkzeug.local import LocalProxy


if t.TYPE_CHECKING:
    from .dispatcher import wsgi
    from .ctx import _AppCtxGlobals, RequestContext
    from .ctx import AppContext
    from .wrappers import Request
    from .session import SessionSignalMixin

_no_app_msg = (
    "Working outside of application context. "
    "This typically means that you attempted to use functionality "
    "that needed an active application context. Consult "
    "the documentation on testing for more information."
)
_cv_app: ContextVar[AppContext] = ContextVar("simplerr.app_ctx")

app_ctx: AppContext = LocalProxy( # type: ignore[assignment]
    _cv_app
)
current_app: wsgi = LocalProxy(  # type: ignore[assignment]
    _cv_app, "app"
)
g: _AppCtxGlobals = LocalProxy( # type: ignore[assignment]
    _cv_app, "g"
)

_cv_request: ContextVar[RequestContext] = ContextVar("simplerr.request_ctx")
request_ctx: RequestContext = LocalProxy( # type: ignore[assignment]
    _cv_request
)
request: Request = LocalProxy( # type: ignore[assignment]
    _cv_request, "request"
)
session: SessionSignalMixin = LocalProxy( # type: ignore[assignment]
    _cv_request, "session"
)