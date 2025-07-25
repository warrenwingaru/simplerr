import collections.abc as c
import hashlib
import typing as t
from datetime import datetime, timezone, timedelta

from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.datastructures import CallbackDict


class SessionSignalMixin(c.MutableMapping):
    @property
    def permanent(self) -> bool:
        return self.get("_permanent", False)

    @permanent.setter
    def permanent(self, value: bool) -> None:
        self["_permanent"] = value

    new = False
    modified = True
    accessed = True


class SecureCookieSession(CallbackDict, SessionSignalMixin):
    """Base class for sessions based on signed cookies"""
    modified = False
    accessed = True

    def __init__(self, initial: t.Union[c.Mapping, c.Iterable, None] = None) -> None:
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

    def make_null_session(self, app) -> NullSession:
        return self.null_session_class()

    def is_null_session(self, obj: t.Any) -> bool:
        return isinstance(obj, self.null_session_class)

    def get_cookie_name(self, app) -> str:
        return app.config.get("SESSION_COOKIE_NAME")

    def get_cookie_domain(self, app) -> t.Optional[str]:
        return app.config.get("SESSION_COOKIE_DOMAIN")

    def get_cookie_path(self, app) -> t.Optional[str]:
        return app.config.get("SESSION_COOKIE_PATH") or app.config.get("APPLICATION_ROOT")

    def get_cookie_httponly(self, app) -> bool:
        return app.config.get("SESSION_COOKIE_HTTPONLY")

    def get_cookie_secure(self, app) -> bool:
        return app.config.get("SESSION_COOKIE_SECURE")

    def get_cookie_samesite(self, app) -> t.Optional[str]:
        return app.config.get("SESSION_COOKIE_SAMESITE")

    def get_expiration_time(self, app, session: SessionSignalMixin) -> t.Union[datetime, None]:
        if session.permanent:
            return datetime.now(timezone.utc) + app.config.get("PERMANENT_SESSION_LIFETIME", timedelta(days=31))
        return None

    def should_set_cookie(self, app, session: SessionSignalMixin) -> bool:
        return session.modified or app.config["SESSION_REFRESH_EACH_REQUEST"]

    def get_signing_serializer(self, app) -> t.Optional[URLSafeTimedSerializer]:
        secret_key = app.config.get("SECRET_KEY", None)
        if not secret_key:
            return None

        keys: list[t.Union[str, bytes]] = []

        fallbacks = app.config.get('SECRET_KEY_FALLBACKS', None)
        if fallbacks:
            keys.extend(fallbacks)

        keys.append(secret_key)
        return URLSafeTimedSerializer(
            keys,
            salt=self.salt,
            signer_kwargs={
                "key_derivation": self.key_derivation,
                "digest_method": self.digest_method,
            }
        )

    def open_session(self, app, request) -> t.Optional[SecureCookieSession]:
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

    def save_session(self, app, session: SessionSignalMixin, response) -> None:
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
