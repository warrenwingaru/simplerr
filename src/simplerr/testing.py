from __future__ import annotations

from copy import copy
from urllib.parse import urlsplit

from werkzeug.wrappers import Request as BaseRequest

from simplerr.dispatcher import wsgi

try:
    import importlib.metadata as importlib
except ImportError:
    import importlib_metadata as importlib
import typing as  t
import werkzeug.test

_werkzeug_version = None

if t.TYPE_CHECKING:
    from _typeshed.wsgi import WSGIEnvironment

class EnvironBuilder(werkzeug.test.EnvironBuilder):
    def __init__(
            self,
            app: wsgi,
            path: str = "/",
            base_url: t.Optional[str] = None,
            subdomain: t.Optional[str] = None,
            uri_scheme: t.Optional[str] = None,
            *args,
            **kwargs
    ):
        assert not (base_url or subdomain or uri_scheme) or (
            base_url is not None
        ) != bool(subdomain or uri_scheme), "Cannot pass 'subdomain' or 'uri_scheme' with 'base_url' "

        if base_url is None:
            http_host = "localhost"

            if subdomain:
                http_host = f"{subdomain}.{http_host}"

            if uri_scheme is None:
                uri_scheme = "http"

            url = urlsplit(path)
            base_url = (
                f'{url.scheme or uri_scheme}://{url.netloc or http_host}/'
            )
            path = url.path
            if url.query:
                path += f"?{url.query}"
        self.app = app
        super().__init__(path, base_url, *args, **kwargs)



def _get_werkzeug_version():
    global _werkzeug_version

    if not _werkzeug_version:
        _werkzeug_version = importlib.version("werkzeug")

    return _werkzeug_version


class SimplerrClient(werkzeug.test.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.environ_base = {
            'REMOTE_ADDR': '127.0.0.1',
            'HTTP_USER_AGENT': f'werkzeug/{_get_werkzeug_version()}',
        }

    def _copy_environ(self, other: WSGIEnvironment) -> WSGIEnvironment:
        return {**self.environ_base, **other}

    def request_from_builder_args(
            self,
            args: t.Any,
            kwargs: t.Any,
    ):
        kwargs['environ_base'] = self._copy_environ(kwargs.get('environ_base', {}))
        builder = EnvironBuilder(self.application, *args, **kwargs)

        try:
            return builder.get_request()
        finally:
            builder.close()