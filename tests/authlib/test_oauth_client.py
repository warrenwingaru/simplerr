import os
from pathlib import Path
from unittest import TestCase, mock

from authlib.common.urls import url_decode, urlparse
from authlib.integrations.base_client import OAuthError
from authlib.jose import JsonWebKey
from authlib.oidc.core.grants.util import generate_id_token
from werkzeug.wrappers import Response, Request
from werkzeug.contrib.sessions import Session
from werkzeug.test import Client, EnvironBuilder

import pytest

import simplerr.dispatcher
from simplerr.authlib import OAuth
from simplerr.session import FileSystemSessionStore
from tests.authlib.util import mock_send_value, get_bearer_token

mock_session = mock.MagicMock(spec=Session)
mock_session.sid = 'test-session-id'
mock_session.should_save = True

common_config = {
    'DEV_CLIENT_ID': 'dev-client-id',
    'DEV_CLIENT_SECRET': 'dev-client-secret',
    'DEV_ACCESS_TOKEN_PARAMS': {"foo": "foo-1", "bar": "bar-2"}}

class RequestClient:
    def __init__(self):
        self.session_store = FileSystemSessionStore()
        self._session = None
        self.cookies = {}

    def get(self, path, **kwargs):
        builder = EnvironBuilder(method='GET', path=path, **kwargs)
        env = builder.get_environ()
        request = Request(env)

        if self._session is None:
            self._session = self.session_store.new()
        request.session = self._session

        return request

    def post(self, path, **kwargs):
        builder = EnvironBuilder(method='POST', path=path, **kwargs)
        env = builder.get_environ()
        request = Request(env)
        if self._session is None:
            self._session = self.session_store.new()
        request.session = self._session
        return request

    @property
    def session(self):
        if self._session is None:
            self._session = self.session_store.new()
            self._session.save(self._session)
        return self._session


class SimplerrOAuthTest(TestCase):
    def setUp(self):
        super().setUp()
        self.factory = RequestClient()

    def test_register_factory(self):
        oauth = OAuth(config=lambda oauth, name, params: common_config)
        oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            request_token_url="https://127.0.0.1:5000/request-token",
            api_base_url="http://127.0.0.1:5000/api",
            access_token_url="http://127.0.0.1:5000/oauth/token",
            authorize_url="http://127.0.0.1:5000/oauth/authorize",
        )
        self.assertEqual(oauth.dev.name, "dev")
        self.assertEqual(oauth.dev.client_id, "dev")


    def test_register_remote_app(self):
        oauth = OAuth(config=common_config)
        with pytest.raises(AttributeError):
            oauth.dev # noqa:8018

        oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            request_token_url="https://127.0.0.1:5000/request-token",
            api_base_url="http://127.0.0.1:5000/api",
            access_token_url="http://127.0.0.1:5000/oauth/token",
            authorize_url="http://127.0.0.1:5000/oauth/authorize",
        )
        self.assertEqual(oauth.dev.name, "dev")
        self.assertEqual(oauth.dev.client_id, "dev")

    def test_register_with_overwrite(self):
        oauth = OAuth(config=common_config)
        oauth.register(
            "dev_overwrite",
            overwrite=True,
            client_id="dev",
            client_secret="dev",
            request_token_url="https://127.0.0.1:5000/request-token",
            api_base_url="http://127.0.0.1:5000/api",
            access_token_url="http://127.0.0.1:5000/oauth/token",
            access_token_params={"foo": "foo"},
            authorize_url="http://127.0.0.1:5000/oauth/authorize",
        )
        self.assertEqual(oauth.dev_overwrite.client_id, "dev")
        self.assertEqual(oauth.dev_overwrite.access_token_params["foo"], "foo")

    def test_oauth1_authorize(self):
        request = self.factory.get('/login')
        request.session = self.factory.session
        oauth = OAuth()
        client = oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            request_token_url="https://127.0.0.1:5000/request-token",
            api_base_url="https://127.0.0.1:5000/api",
            access_token_url="https://127.0.0.1:5000/oauth/token",
            authorize_url="https://127.0.0.1:5000/oauth/authorize",
        )

        with mock.patch("requests.sessions.Session.send") as send:
            send.return_value = mock_send_value("oauth_token=foo&oauth_verifier=baz")

            resp = client.authorize_redirect(request)
            assert resp.status_code == 302
            url = resp.headers['Location']
            assert "oauth_token=foo" in url

        request2= self.factory.get(f'{url}&oauth_verifier=baz')
        request2.session = request.session
        with mock.patch("requests.sessions.Session.send") as send:
            send.return_value = mock_send_value("oauth_token=a&oauth_token_secret=b")
            token = client.authorize_access_token(request2)
            self.assertEqual(token["oauth_token"], "a")

    def test_oauth2_authorize(self):
        request = self.factory.get('/login')
        request.session = self.factory.session
        oauth = OAuth()
        client = oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            api_base_url="https://127.0.0.1:5000/api",
            access_token_url="https://127.0.0.1:5000/oauth/token",
            authorize_url="https://127.0.0.1:5000/oauth/authorize",
        )
        rv = client.authorize_redirect(request)
        self.assertEqual(rv.status_code, 302)
        url = rv.headers['Location']
        self.assertIn("state=", url)
        state = dict(url_decode(urlparse.urlparse(url).query))['state']

        with mock.patch("requests.sessions.Session.send") as send:
            send.return_value = mock_send_value(get_bearer_token())
            builder = EnvironBuilder(method="GET", path='/authorize?state={}'.format(state))
            request2 = builder.get_request()
            request2.session = request.session

            token = client.authorize_access_token(request2)
            self.assertEqual(token["access_token"], "a")


    def test_oauth2_authorize_access_denied(self):
        oauth = OAuth()
        client = oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            api_base_url="https://127.0.0.1:5000/api",
            access_token_url="https://127.0.0.1:5000/oauth/token",
            authorize_url="https://127.0.0.1:5000/oauth/authorize",
        )
        with mock.patch("requests.sessions.Session.send") as send:
            request = self.factory.get('/login')
            request.session = self.factory.session
            self.assertRaises(OAuthError, client.authorize_access_token, request)


    def test_oauth2_authorize_code_verifier(self):
        request = self.factory.get('/login')
        request.session = self.factory.session

        oauth = OAuth()
        client = oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            api_base_url="https://127.0.0.1:5000/api",
            access_token_url="https://127.0.0.1:5000/oauth/token",
            authorize_url="https://127.0.0.1:5000/oauth/authorize",
            client_kwargs={"code_challenge_method": "S256"}
        )
        state = 'foo'
        code_verifier = 'bar'
        rv = client.authorize_redirect(
            request, 'https://a.b/c',
            state = state,
            code_verifier = code_verifier
        )
        self.assertEqual(rv.status_code, 302)
        url = rv.headers['Location']
        self.assertIn("state=", url)
        self.assertIn("code_challenge=", url)

        with mock.patch("requests.sessions.Session.send") as send:
            send.return_value = mock_send_value(get_bearer_token())

            request2 = self.factory.get('/authorize?state={}'.format(state))
            request2.session = request.session

            token = client.authorize_access_token(request2)
            self.assertEqual(token["access_token"], "a")

    def test_openid_authorize(self):
        request = self.factory.get('/login')
        request.session = self.factory.session
        secret_key = JsonWebKey.import_key('secret', {'kty': 'oct', 'kid': 'f'})

        oauth = OAuth()
        client = oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            jwks={"keys": [secret_key.as_dict()]},
            api_base_url="https://127.0.0.1:5000/api",
            access_token_url="https://127.0.0.1:5000/oauth/token",
            authorize_url="https://127.0.0.1:5000/oauth/authorize",
            client_kwargs={'scope': 'openid profile'}
        )

        resp = client.authorize_redirect(request, 'https://b.com/bar')
        self.assertEqual(resp.status_code, 302)
        url = resp.headers['location']
        self.assertIn('nonce=', url)
        query_data = dict(url_decode(urlparse.urlparse(url).query))

        token = get_bearer_token()
        token['id_token'] = generate_id_token(
            token, {'sub': '123'}, secret_key,
            alg='HS256', iss='https://i.b',
            aud='dev', exp=3600, nonce=query_data['nonce']
        )
        state = query_data['state']
        with mock.patch('requests.sessions.Session.send') as send:
            send.return_value = mock_send_value(token)

            request2 = self.factory.get('/authorize?state={}&code=foo'.format(state))
            request2.session = request.session

            token = client.authorize_access_token(request2)
            self.assertEqual(token['access_token'], 'a')
            self.assertIn('userinfo', token)
            self.assertEqual(token['userinfo']['sub'], '123')

    def test_oath2_access_token_with_post(self):
        oauth = OAuth()
        client = oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            api_base_url="https://127.0.0.1:5000/api",
            access_token_url="https://127.0.0.1:5000/oauth/token",
            authorize_url="https://127.0.0.1:5000/oauth/authorize",
        )
        payload = {'code': 'a', 'state': 'b'}

        with mock.patch('requests.sessions.Session.send') as send:
            send.return_value = mock_send_value(get_bearer_token())
            request = self.factory.post('/token', data=payload)
            request.session = self.factory.session
            request.session['_state_dev_b'] = {'data': {}}
            token = client.authorize_access_token(request)
            self.assertEqual(token['access_token'], 'a')

    def test_with_fetch_token_in_oauth(self):
        def fetch_token(name, request):
            return {'access_token': name, 'token_type': 'bearer'}

        oauth = OAuth(fetch_token=fetch_token)
        client = oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            api_base_url="https://127.0.0.1:5000/api",
            access_token_url="https://127.0.0.1:5000/oauth/token",
            authorize_url="https://127.0.0.1:5000/oauth/authorize",
        )

        def fake_send(sess, req, **kwargs):
            self.assertEqual(sess.token['access_token'], 'dev')
            return mock_send_value(get_bearer_token())

        with mock.patch('requests.sessions.Session.send', fake_send):
            request= self.factory.get('/login')
            client.get('/user', request=request)


    def test_with_fetch_token_in_register(self):
        def fetch_token(request):
            return {'access_token': 'dev', 'token_type': 'bearer'}

        oauth = OAuth()
        client = oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            api_base_url="https://127.0.0.1:5000/api",
            access_token_url="https://127.0.0.1:5000/oauth/token",
            authorize_url="https://127.0.0.1:5000/oauth/authorize",
            fetch_token=fetch_token
        )

        def fake_send(sess, req, **kwargs):
            self.assertEqual(sess.token['access_token'], 'dev')
            return mock_send_value(get_bearer_token())

        with mock.patch('requests.sessions.Session.send', fake_send):
            request= self.factory.get('/login')
            client.get('/user', request=request)

    def test_request_without_token(self):
        oauth = OAuth()
        client = oauth.register(
            "dev",
            client_id="dev",
            client_secret="dev",
            api_base_url="https://i.b/api",
            access_token_url="https://i.b/token",
            authorize_url="https://i.b/authorize",
        )

        def fake_send(sess, req, **kwargs):
            auth = req.headers.get('Authorization')
            self.assertIsNone(auth)
            resp = mock.MagicMock()
            resp.text = 'hi'
            resp.status_code = 200
            return resp

        with mock.patch('requests.sessions.Session.send', fake_send):
            resp = client.get('/api/user', withhold_token=True)
            self.assertEqual(resp.text, 'hi')
            self.assertRaises(OAuthError, client.get, 'https://i.b/api/user')