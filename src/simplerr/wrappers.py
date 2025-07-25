import json
import logging
from functools import lru_cache
import typing as t

from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import (
    Response as BaseResponse,
    Request as BaseRequest
)
from werkzeug.routing import Rule

from .cors import CORS
from .events import WebEvents
from .session import SessionSignalMixin

logger = logging.getLogger(__name__)


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

    _cached_json: t.Optional[t.Any] = None
    view_events = WebEvents()
    session: t.Optional[SessionSignalMixin] = None

    @property
    def endpoint(self):
        """The endpoint that matched the request URL."""
        if self.url_rule is not None:
            return self.url_rule.endpoint
        return None

    @property
    @lru_cache(maxsize=1)
    def json(self):
        """Adds support for JSON and other niceties"""
        if not self._cached_json:
            try:
                self._cached_json = json.loads(self.data)
            except (ValueError, UnicodeDecodeError):
                logger.error(f"Error decoding JSON: {self.data}")
                self._cached_json = None
        return self._cached_json


class Response(BaseResponse):
    default_mimetype: t.Optional[str] = "text/html"
    # autocorrect_location_header = False
