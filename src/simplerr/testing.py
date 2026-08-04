from __future__ import annotations

import importlib.metadata
import typing as t
from urllib.parse import urlsplit

import werkzeug.test
from werkzeug.test import Client

from simplerr import dispatcher


class EnvironBuilder(werkzeug.test.EnvironBuilder):
    def __init__(
            self,
            app: dispatcher.wsgi,
            path: str = "/",
            base_url: t.Optional[str] = None,
                 subdomain: t.Optional[str] = None,
            url_scheme: t.Optional[str] = None,
            *args: t.Any,
            **kwargs: t.Any
    ) -> None:
        assert not (base_url or subdomain or url_scheme) or (
            base_url is not None
        ) != bool(subdomain or url_scheme), (
            'Cannot pass "subdomain" or "url_scheme" with "base_url"'
        )

        if base_url is None:
            http_host = app.config.get("SERVER_NAME") or "localhost"
            app_root = app.config["APPLICATION_ROOT"]

            if subdomain:
                http_host = f"{subdomain}.{http_host}"

            if url_scheme is None:
                url_scheme = app.config["PREFERRED_URL_SCHEME"]

            url = urlsplit(path)
            base_url = (
                f"{url.scheme or url_scheme}://{url.netloc or http_host}"
                f"{app_root.lstrip('/')}"
            )
            path = url.path

            if url.query:
                path = f"{path}?{url.query}"

        self.app = app
        super().__init__(path, base_url, *args, **kwargs)




werkzeug_version = ""


def _get_werkzeug_version() -> str:
    global _werkzeug_version

    if not _werkzeug_version:
        _werkzeug_version = importlib.metadata.version("werkzeug")

    return _werkzeug_version


class SimplerrClient(Client):
    application: dispatcher.wsgi

    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().__init__(*args, **kwargs)
        self.environ_base = {
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_USER_AGENT": f"Werkzeug/{_get_werkzeug_version()}",
        }
