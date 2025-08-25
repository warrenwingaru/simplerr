import typing as t

from werkzeug.exceptions import HTTPException, BadRequest
from werkzeug.routing import Rule
from werkzeug.wrappers import (
    Response as BaseResponse,
    Request as BaseRequest
)

from . import json
from .cors import CORS
from .events import WebEvents
from .globals import current_app
from .session import SessionSignalMixin


class Request(BaseRequest):
    """The request object used by default in Simplerr. Remembers the
    matched endpoint and view arguments.
    """

    #: The internal URL rule that matched the request
    #:
    #: .. versionadded: 0.18.3
    url_rule: t.Optional[Rule] = None

    #: A dict of view arguments that matched the request. If an exception
    #: happened when matching, this will be ``None``.
    view_args: t.Optional[t.Any] = None

    match: t.Optional[t.Any] = None

    routing_exception: t.Optional[HTTPException] = None
    cors: t.Optional[CORS] = None
    cwd: t.Optional[str] = None
    json_module = json

    view_events = WebEvents()
    session: t.Optional[SessionSignalMixin] = None

    @property
    def endpoint(self):
        """The endpoint that matched the request URL."""
        if self.url_rule is not None:
            return self.url_rule.endpoint
        return None

    def on_json_loading_failed(self, e: t.Optional[ValueError]) -> t.Any:
        try:
            return super().on_json_loading_failed(e)
        except BadRequest as ebr:
            if current_app and current_app.debug:
                raise
            raise BadRequest() from ebr


class Response(BaseResponse):
    default_mimetype: t.Optional[str] = "text/html"
    # autocorrect_location_header = False
