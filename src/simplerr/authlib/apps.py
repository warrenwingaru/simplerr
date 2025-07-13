from authlib.integrations.base_client import BaseApp, OAuth2Mixin, OpenIDMixin, OAuthError, OAuth1Mixin
from authlib.integrations.requests_client import OAuth2Session, OAuth1Session
from simplerr.dispatcher import Request
from simplerr import web


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

class SimplerrOAuth1App(SimplerrMixin, OAuth1Mixin, BaseApp):
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

class SimplerrOAuth2App(SimplerrMixin, OAuth2Mixin, OpenIDMixin, BaseApp):
    client_cls = OAuth2Session

    def authorize_access_token(self, request: Request, **kwargs):
        """Fetch access token in one step

        :return: A token dict.
        """
        if request.method == "GET":
            error = request.args.get('error')
            if error:
                description = request.args.get('error_description')
                raise OAuthError(error=error, description=description)
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
