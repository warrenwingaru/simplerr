import os


def get_debug_flag() -> bool:
    val = os.environ.get('SIMPLERR_DEBUG')
    return bool(val and val.lower() not in {'0', 'false', 'no'})
