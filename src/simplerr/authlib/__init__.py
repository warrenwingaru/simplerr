try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    from importlib_metadata import version, PackageNotFoundError

required_version = "1.2.1"
try:
    from authlib.integrations.base_client import BaseOAuth
    from authlib.integrations.base_client import OAuthError

    try:
        authlib_version = version("authlib")
        if authlib_version != required_version:
            raise RuntimeError(f'Authlib {required_version} required, but version {authlib_version} is installed')
    except PackageNotFoundError:
        raise RuntimeError(f'Authlib {required_version} must be installed')
except ImportError:
    raise RuntimeError(f"Authlib {required_version} must be installed")

from .integration import SimplerrIntegration
from .apps import SimplerrOAuth2App, SimplerrOAuth1App


class OAuth(BaseOAuth):
    oauth1_client_cls = SimplerrOAuth1App
    oauth2_client_cls = SimplerrOAuth2App
    framework_integration_cls = SimplerrIntegration

    def __init__(self, config=None, cache=None, fetch_token=None, update_token=None):
        super().__init__(
            cache=cache, fetch_token=fetch_token, update_token=update_token
        )
        self.config = config


__all__ = [
    'OAuth',
    'SimplerrOAuth1App',
    'SimplerrOAuth2App',
    'SimplerrIntegration',
    'OAuthError'
]
