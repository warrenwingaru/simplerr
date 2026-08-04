# Import wsgi
from .dispatcher import wsgi
from .config import Config as Config
from .dispatcher import wsgi as Simplerr
from .globals import current_app as current_app
from .globals import g as g
from .globals import request as request
from .globals import session as session

# Import Core Web
from .web import web
from .version import __version__

# Import Grammar Helpers
from .methods import GET, POST, PUT, DELETE, PATCH
from .cors import CORS
from .wrappers import Request as Request
from .wrappers import Response as Response

# flake8: noqa
__version__ = __version__
