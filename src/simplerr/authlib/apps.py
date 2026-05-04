from authlib.common.security import generate_token
from authlib.common.urls import add_params_to_uri
from authlib.integrations.base_client import BaseApp, OAuth2Mixin, OpenIDMixin, OAuthError, OAuth1Mixin
from authlib.integrations.requests_client import OAuth2Session, OAuth1Session
from authlib.oauth2 import OAuth2Error

from simplerr.dispatcher import Request
from simplerr import web

# TODO: remove when updated to authlib>=1.7.0
class CustomBaseApp(BaseApp):
    def create_logout_url(
            self,
            post_logout_redirect_uri=None,
            id_token_hint=None,
            state=None,
            **kwargs
    ):
        """Generate the end session URL for RP-initiated Logout.

        :param post_logout_redirect_uri: URI to redirect to after Logout.
        :param id_token_hint: ID Token for previously issued to the RP
        :param state: Opaque value for maintaining state
        :param kwargs: Extra parameters (client_id, logout_hint, ui_locales)
        :return: dict with 'url' and 'state' keys.
        """
        metadata = self.load_server_metadata()
        end_session_endpoint = metadata.get('end_session_endpoint', None)

        if not end_session_endpoint:
            raise RuntimeError("Missing 'end_session_endpoint' in metadata.")

        params = {}
        if id_token_hint:
            params['id_token_hint'] = id_token_hint
        if post_logout_redirect_uri:
            params['post_logout_redirect_uri'] = post_logout_redirect_uri
            if state is None:
                state = generate_token(20)
            params['state'] = state

        for key in ("client_id", "logout_hint", "ui_locales"):
            if key in kwargs:
                params[key] = kwargs.pop(key)

        url = add_params_to_uri(end_session_endpoint, params)
        return {'url': url, 'state': state}

class SimplerrMixin:

    def save_authorize_data(self, request: Request, **kwargs):
        state = kwargs.pop('state', None)
        if state:
            self.framework.set_state_data(request.session, state, kwargs)
        else:
            raise RuntimeError("Missing state value.")

    def authorize_redirect(self, request: Request, redirect_uri=None, **kwargs):
        """Create a HTTP redirect for Authorization Endpoint.

        :param request: HTTP request instance from simplerr
        :param redirect_uri: Callback or redirect URI for authorization.
        :param kwargs: Extra parameters to include.
        :return: A HTTP redirect response.
        """
        rv = self.create_authorization_url(redirect_uri, **kwargs)
        self.save_authorize_data(request, redirect_uri=redirect_uri, **rv)
        return web.redirect(rv['url'])

class SimplerrOAuth1App(SimplerrMixin, OAuth1Mixin, CustomBaseApp):
    client_cls = OAuth1Session

    def authorize_access_token(self, request: Request, **kwargs):
        """Fetch access token in one step.

        :param request: HTTP request instance from simplerr
        :return: A token dict.
        """
        params = request.args.to_dict()
        state = params.get("oauth_token")
        if not state:
            raise OAuthError(description='Missing "oauth_token" parameter')

        data = self.framework.get_state_data(request.session, state)
        if not data:
            raise OAuthError(description='Invalid "oauth_token" parameter')

        params["request_token"] = data["request_token"]
        params.update(kwargs)
        self.framework.clear_state_data(request.session, state)
        return self.fetch_access_token(**params)

class SimplerrOAuth2App(SimplerrMixin, OAuth2Mixin, OpenIDMixin, CustomBaseApp):
    client_cls = OAuth2Session

    def authorize_access_token(self, request: Request, **kwargs):
        """Fetch access token in one step

        :return: A token dict.
        """
        if request.method == "GET":
            error = request.args.get('error')
            if error:
                description = request.args.get('error_description')
                raise OAuth2Error(error=error, description=description)
            params = {
                "code": request.args.get('code'),
                "state": request.args.get('state'),
            }
        else:
            params = {
                "code": request.form.get('code'),
                "state": request.form.get('state'),
            }

        state_data = self.framework.get_state_data(request.session, params.get('state'))
        self.framework.clear_state_data(request.session, params.get("state"))
        params = self._format_state_params(state_data, params)

        claims_options = kwargs.pop('claims_options', None)
        leeway = kwargs.pop('leeway', 120)
        token = self.fetch_access_token(**params, **kwargs)

        if "id_token" in token and "nonce" in state_data:
            userinfo = self.parse_id_token(
                token,
                nonce=state_data['nonce'],
                claims_options=claims_options,
                leeway=leeway
            )
            token['userinfo'] = userinfo

        return token

    def logout_redirect(
            self, request, post_logout_redirect_uri=None, id_token_hint=None, **kwargs
    ):
        """Create a HTTP redirect for End Session Endpoint (RP-initiated Logout).

        :param request: HTTP request instance from simplerr
        :param post_logout_redirect_uri: URI to redirect to after logging out.
        :param id_token_hint: ID Token previously issued to the RP
        :param kwargs: Extra parameters (state, client_id, logout_hint, ui_locales).
        :return: A HTTP redirect response.
        """
        result = self.create_logout_url(
            post_logout_redirect_uri=post_logout_redirect_uri,
            id_token_hint=id_token_hint,
            **kwargs
        )
        if result.get('state', None):
            self.framework.set_state_data(request.session, result['state'], {
                'post_logout_redirect_uri': post_logout_redirect_uri,
            })
        return web.redirect(result['url'])

    def validate_logout_response(self, request):
        """Validate the state parameter from the logout callback

        :param request: HTTP request instance from simplerr
        :return: The state data dict
        :raises OAuth2Error: if state is missing or invalid
        """
        state = request.args.get('state')
        if not state:
            raise OAuth2Error(description='Missing "state" parameter')
        state_data = self.framework.get_state_data(request.session, state)
        if not state_data:
            raise OAuth2Error(description='Invalid "state" parameter')

        self.framework.clear_state_data(request.session, state)
        return state_data
