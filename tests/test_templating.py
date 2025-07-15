import os
import pytest
from simplerr.template import T

@pytest.fixture
def renderer():
    cwd = os.path.dirname(__file__)
    return T(cwd)

def test_pure_html(renderer):
    expect="Hello World"
    rendered = renderer.render('assets/html/01_pure_html.html')
    assert expect == rendered

def test_echo_back(renderer):
    expect="Hello World and Echo Back"
    stash= {"msg":expect}
    rendered = renderer.render('assets/html/02_echo.html', stash)
    assert expect == rendered


