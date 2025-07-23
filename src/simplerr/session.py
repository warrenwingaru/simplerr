from __future__ import annotations

import collections.abc as c
import hashlib
import typing as t
from datetime import datetime, timezone, timedelta

from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.datastructures import CallbackDict

if t.TYPE_CHECKING:
    from .dispatcher import wsgi
    from .wrappers import Response, Request


class SessionSignalMixin(c.MutableMapping[str, t.Any]):
    @property
    def permanent(self) -> bool:
        return self.get("_permanent", False)

    @permanent.setter
    def permanent(self, value: bool) -> None:
        self["_permanent"] = value

    new = False
    modified = True
    accessed = True


class SecureCookieSession(CallbackDict[str, t.Any], SessionSignalMixin):
    """Base class for sessions based on signed cookies"""
    modified = False
    accessed = True

    def __init__(self, initial: t.Union[c.Mapping[str, t.Any], c.Iterable[tuple[str, t.Any]], None] = None) -> None:
        def on_update(self):
            self.modified = True
            self.accessed = True

        super().__init__(initial, on_update)

    def __getitem__(self, key: str) -> t.Any:
        self.accessed = True
        return super().__getitem__(key)

    def get(self, key: str, default: t.Any = None) -> t.Any:
        self.accessed = True
        return super().get(key, default)

    def setdefault(self, key: str, default: t.Any = None) -> t.Any:
        self.accessed = True
        return super().setdefault(key, default)


class NullSession(SecureCookieSession):
    """Class used to generate nicer error messages if sessions are not
    available.  Will still allow read-only access to the empty session but
    but fail on setting
    """

    def _fail(self, *args, **kwargs):
        raise RuntimeError("The session is unavailable because no secret "
                           "key was set.  Set the secret_key on the "
                           "application to something unique and secret.")

    __setitem__ = __delitem__ = clear = pop = popitem = update = setdefault = _fail
    del _fail


def _lazy_sha1(string: bytes = b'') -> t.Any:
    return hashlib.sha1(string)


class SecureCookieSessionInterface(object):
    """A simple session interface that stores data in signed cookies.
    This is the default session interface used by :class:`Flask`.
    """

    salt = "cookie-session"
    digest_method = staticmethod(_lazy_sha1)
    key_derivation = "hmac"
    session_class = SecureCookieSession
    null_session_class = NullSession

    def make_null_session(self, app: wsgi) -> NullSession:
        return self.null_session_class()

    def is_null_session(self, obj: t.Any) -> bool:
        return isinstance(obj, self.null_session_class)

    def get_cookie_name(self, app: wsgi) -> str:
        return app.config.get("SESSION_COOKIE_NAME", "sessionfast")

    def get_cookie_domain(self, app: wsgi) -> t.Optional[str]:
        return app.config.get("SESSION_COOKIE_DOMAIN", None)

    def get_cookie_path(self, app: wsgi) -> t.Optional[str]:
        return app.config.get("SESSION_COOKIE_PATH", None)

    def get_cookie_httponly(self, app: wsgi) -> bool:
        return app.config.get("SESSION_COOKIE_HTTPONLY", True)

    def get_cookie_secure(self, app: wsgi) -> bool:
        return app.config.get("SESSION_COOKIE_SECURE", False)

    def get_cookie_samesite(self, app: wsgi) -> t.Optional[str]:
        return app.config.get("SESSION_COOKIE_SAMESITE", None)

    def get_expiration_time(self, app: wsgi, session: SessionSignalMixin) -> t.Union[datetime, None]:
        if session.permanent:
            return datetime.now(timezone.utc) + app.config.get("PERMANENT_SESSION_LIFETIME", timedelta(days=31))
        return None

    def should_set_cookie(self, app: wsgi, session: SessionSignalMixin) -> bool:
        return session.modified or app.config["SESSION_REFRESH_EACH_REQUEST"]

    def get_signing_serializer(self, app: wsgi) -> t.Optional[URLSafeTimedSerializer]:
        secret_key = app.config.get("SECRET_KEY", None)
        if not secret_key:
            return None

        keys: list[t.Union[str, bytes]] = [secret_key]
        return URLSafeTimedSerializer(
            keys,
            salt=self.salt,
            signer_kwargs={
                "key_derivation": self.key_derivation,
                "digest_method": self.digest_method,
            }
        )

    def open_session(self, app: wsgi, request: Request) -> t.Optional[SecureCookieSession]:
        s = self.get_signing_serializer(app)
        if s is None:
            return None
        val = request.cookies.get(self.get_cookie_name(app))
        if not val:
            return self.session_class()
        max_age = 3600
        try:
            data = s.loads(val, max_age=max_age)
            return self.session_class(data)
        except BadSignature:
            return self.session_class()

    def save_session(self, app: wsgi, session: SessionSignalMixin, response: Response) -> None:
        name = self.get_cookie_name(app)
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        secure = self.get_cookie_secure(app)
        httponly = self.get_cookie_httponly(app)
        samesite = self.get_cookie_samesite(app)

        if session.accessed:
            response.vary.add("Cookie")

        if not session:
            if session.modified:
                response.delete_cookie(
                    name,
                    domain=domain,
                    path=path,
                    secure=secure,
                    httponly=httponly,
                    samesite=samesite,
                )
                response.vary.add("Cookie")
            return

        if not self.should_set_cookie(app, session):
            return

        expires = self.get_expiration_time(app, session)
        val = self.get_signing_serializer(app).dumps(dict(session))
        response.set_cookie(
            name,
            val,
            expires=expires,
            httponly=httponly,
            domain=domain,
            path=path,
            secure=secure,
            samesite=samesite,
        )
        response.vary.add("Cookie")

# class MMemorySessionStore(SessionStore, SessionSignalMixin):
#     """TODO: Flesh out, sourced from
#     https://github.com/pallets/werkzeug/blob/master/examples/contrib/sessions.py
#
#     Review Flask Secure Sessions
#     https://github.com/pallets/flask/blob/master/flask/sessions.py
#
#     How to Use
#     ----------
#
#     def application(environ, start_response):
#         session = environ['werkzeug.session']
#         session['visit_count'] = session.get('visit_count', 0) + 1
#
#         start_response('200 OK', [('Content-Type', 'text/html')])
#         return ['''
#             <!doctype html>
#             <title>Session Example</title>
#             <h1>Session Example</h1>
#             <p>You visited this page %d times.</p>
#         ''' % session['visit_count']]
#
#
#     def make_app():
#         return SessionMiddleware(application, MemorySessionStore())
#     """
#
#     def __init__(self, session_class=None):
#         self.COOKIE_NAME = "sessionfast"
#         SessionStore.__init__(self, session_class=None)
#         self.sessions = {}
#
#         # Number of minutes before sessions expire
#         self.expire = 40
#
#     def clean(self):
#         cleanup_sid = []
#
#         # Collect sessions to cleanup
#         for key in self.sessions.keys():
#             accessed = self.sessions[key]["meta"]["accessed"]
#             expiration = datetime.now() - timedelta(minutes=self.expire)
#
#             if accessed < expiration:
#                 cleanup_sid.append(key)
#
#         for expired_sid in cleanup_sid:
#             self.delete(self.get(expired_sid))
#
#     def save(self, session):
#         self.sessions[session.sid] = {
#             "session": session,
#             "meta": {"accessed": datetime.now()},
#         }
#
#     def delete(self, session):
#         self.sessions.pop(session.sid, None)
#
#     def get(self, sid):
#         if not self.is_valid_key(sid) or sid not in self.sessions:
#             return self.new()
#         return self.session_class(self.sessions[sid]["session"], sid, False)
#
#     """
#     From: http://werkzeug.pocoo.org/docs/0.14/contrib/sessions/
#
#     For better flexibility it’s recommended to not use the middleware but the store
#     and session object directly in the application dispatching:
#
#     ::
#
#         session_store = FilesystemSessionStore()
#
#         def application(environ, start_response):
#             request = Request(environ)
#             sid = request.cookies.get('cookie_name')
#             if sid is None:
#                 request.session = session_store.new()
#             else:
#                 request.session = session_store.get(sid)
#             response = get_the_response_object(request)
#             if request.session.should_save:
#                 session_store.save(request.session)
#                 response.set_cookie('cookie_name', request.session.sid)
#             return response(environ, start_response)
#
#
#     The following provides a helper method for pre request and post request
#     process.
#
#     def pre_response(self, request):
#         print("    > Cleaning Up Sessions")
#         self.clean()
#
#         print("    > Active Session: {}".format( len(self.sessions.keys())))
#         sid = request.cookies.get(MemorySessionStore.COOKIE_NAME)
#         print("    > Pre response session fired, cookie sid is: {}".format(sid))
#
#         if sid is None:
#             request.session = self.new()
#             print("    > Generated new sid: {}".format(request.session.sid))
#         else:
#             request.session = self.get(sid)
#             print("    > Using existing sid: {}".format(request.session.sid))
#
#     def post_response(self, request, response):
#         print("    > Post response session fired, saving sid: {}", request.session.sid)
#
#         if request.session.should_save:
#             print("    > Saving Session to cookie")
#             self.save(request.session)
#             response.set_cookie(MemorySessionStore.COOKIE_NAME,
#                                 request.session.sid)
#
#     """
#
#
# class NoSQLSessionStore(SessionStore):
#     """Todo: Implement TinyDB dict session store"""
#
#     pass
#
#
# class DbSessionStore(SessionStore):
#     """Todo: Implement Db session store"""
#
#     pass


# class FileSystemSessionStore(WerkzeugFilesystemSessionStore, SessionSignalMixin):
#     def __init__(self, session_class=None):
#         # Number of minutes before sessions expire
#         self.expire = 40
#
#         self.COOKIE_NAME = "sessionfast"
#         WerkzeugFilesystemSessionStore.__init__(self, session_class=None)
#
#     def clean(self):
#         pass
