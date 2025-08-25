from __future__ import annotations

import logging
import typing as t

import sys
from werkzeug.local import LocalProxy

from .globals import request

if t.TYPE_CHECKING:
    from .dispatcher import wsgi


@LocalProxy
def wsgi_errors_stream() -> t.TextIO:
    if request:
        return request.environ.get('wsgi.errors')

    return sys.stderr


def has_level_handler(logger: logging.Logger) -> bool:
    level = logger.getEffectiveLevel()
    current = logger

    while current:
        if any(handler.level <= level for handler in current.handlers):
            return True

        if not current.propagate:
            break

        current = current.parent

    return False


default_handler = logging.StreamHandler(wsgi_errors_stream)
default_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
)


def create_logger(app: wsgi) -> logging.Logger:
    logger = logging.getLogger(app.name)

    if app.debug and not logger.level:
        logger.setLevel(logging.DEBUG)

    if not has_level_handler(logger):
        logger.addHandler(default_handler)

    return logger
