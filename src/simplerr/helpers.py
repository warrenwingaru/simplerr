import os
import sys


def get_debug_flag() -> bool:
    val = os.environ.get('SIMPLERR_DEBUG')
    return bool(val and val.lower() not in {'0', 'false', 'no'})

class _CollectErrors:
    def __init__(self):
        self.errors: list[BaseException] = []

    def __enter__(self):
        ...

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            self.errors.append(exc_val)

        return True

    def raise_any(self, message: str) -> None:
        if self.errors:
            if sys.version_info >= (3, 11):
                raise BaseExceptionGroup(message, self.errors)
            else:
                raise self.errors[0]