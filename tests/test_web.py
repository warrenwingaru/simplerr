from unittest import TestCase

import pytest

from simplerr import web, GET, POST, DELETE, PUT, PATCH, Request
from werkzeug.test import EnvironBuilder
import os
from pprint import pprint


"""
This test suite makes extensive use the the werkzeug test framework, it can be
found here: http://werkzeug.pocoo.org/docs/0.14/test/


"""

# Track function ID's before they are wrapped
fn_ids = {}


@web("/simple")
def simple_fn(r):
    return


@web("/response/string")
def string_response_fn(r):
    return ""


@web("/response/dict")
def dict_response_fn(r):
    return {}


@web("/response/file", file=True)
def file_response_fn(r):
    return "assets/html/01_pure_html.html"


@web.filter("echo")
def echo_fn(msg):
    return msg


@web.filter("upper")
def upper_fn(text):
    return upper(text)


def create_env(path, method="GET"):
    from werkzeug.test import EnvironBuilder

    builder = EnvironBuilder(method=method, path=path)
    env = builder.get_environ()

    return env

@pytest.fixture()
def cwd():
    return os.path.dirname(__file__)

def test_check_routes(cwd):
    assert web.destinations[0].endpoint == id(web.destinations[0].fn)
    assert web.destinations[0].fn.__name__ == "simple_fn"
    assert web.destinations[0].route == "/simple"

    assert web.destinations[1].endpoint == id(web.destinations[1].fn)
    assert web.destinations[1].fn.__name__ == "string_response_fn"
    assert web.destinations[1].route == "/response/string"

    assert web.destinations[2].endpoint == id(web.destinations[2].fn)
    assert web.destinations[2].fn.__name__ == "dict_response_fn"
    assert web.destinations[2].route == "/response/dict"

def test_match_simple_route(cwd):
    env = create_env("/simple")
    req = Request(env)
    req.url_rule, req.view_args, req.match = web.match_request(req)
    assert req.match.fn.__name__ == "simple_fn"

def test_process_request(cwd):
    from simplerr.wrappers import Request, Response

    env = create_env("/simple")
    req = Request(env)
    req.cwd = cwd

    resp = web.make_response(req, 'null')
    assert isinstance(resp, Response)
    assert resp.status_code == 200
    assert resp.data == b"null"

def test_response_util(cwd):
    from werkzeug.wrappers import Request, Response

    resp = web.response(None)
    assert isinstance(resp, Response)

def test_filter_decorator(cwd):
    assert "echo" in web.filters

def test_template_util(cwd):
    rv = web.template(cwd, "/assets/html/01_pure_html.html", {})
    assert rv == "Hello World"

def test_request_redirect(cwd):
    from werkzeug.wrappers import Request, Response

    rv = web.response("http://example.com")
    assert isinstance(rv, Response)

def test_request_abort(cwd):
    from werkzeug.exceptions import NotFound, Unauthorized

    with pytest.raises(NotFound):
        web.abort()
    with pytest.raises(Unauthorized):
        web.abort(code=401)

def test_send_files(cwd):
    from simplerr.wrappers import Request, Response

    env = create_env("/response/file")
    req = Request(env)

    req.cwd = cwd
    req.url_rule, req.view_args, req.match = web.match_request(req)

    resp = web.make_response(req, req.match.fn(req, **req.view_args))
    assert isinstance(resp, Response)
    assert resp.status_code == 200

    # Need to disable direct passthrough for testing
    resp.direct_passthrough = False
    assert resp.data == b"Hello World\n"
