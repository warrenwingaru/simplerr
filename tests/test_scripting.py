import pytest

import simplerr.script
import os

@pytest.fixture
def cwd():
    return os.path.dirname(__file__)

def get_script(cwd, route):
    sc = simplerr.script.script(cwd, route)
    return sc.get_script()

def get_module(cwd, route):
    sc = simplerr.script.script(cwd, route)
    return sc.get_module()


def test_path(cwd):
    expect = f'{cwd}/assets/scripts/sc_hello_world.py'
    path = get_script(cwd,'/assets/scripts/sc_hello_world')
    assert expect == path


def test_path_index(cwd):
    expect = f'{cwd}/assets/scripts/index.py'
    path = get_script(cwd, '/assets/scripts')
    assert expect == path


def test_module(cwd):
    expect = "Hello World"
    module = get_module(cwd, '/assets/scripts/sc_hello_world')
    assert expect == module.__description__
