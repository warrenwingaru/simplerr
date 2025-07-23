
# Import Core Web
from .web import web
from .version import __version__

# Import Grammar Helpers
from .methods import GET, POST, PUT, DELETE, PATCH
from .cors import CORS
from .wrappers import Request as Request
from .wrappers import Response as Response
from .dispatcher import Simplerr

# flake8: noqa
__version__ = __version__
