import typing as t
from .methods import POST, GET, DELETE, PUT, PATCH, BaseMethod


class CORS(object):

    """Add basic CORS header support when provided

    More information
    ----------------
    See issue at https://github.com/pallets/werkzeug/issues/131

    Example usage
    -------------

    # Using default values
    @web('/api/login', cors=CORS())
    def login(request):
        return {'success':True}

    # Using custom configuration
    cors=CORS()
    cors.origin="localhost"
    cors.methods=[POST]

    # Will append header to defaults, if you want to reset use `cors.headers=[]`
    cors.headers.append('text/plain')

    # Using default values
    @web('/api/login', cors=cors)
    def login(request):
        return {'success':True}


    """

    DEFAULT_ORIGIN = "*"
    DEFAULT_METHODS = [POST, GET, DELETE, PUT, PATCH]
    DEFAULT_HEADERS = ["Content-Type", "Authorization"]

    def __init__(
            self,
            origin: str = DEFAULT_ORIGIN,
            methods: t.Optional[list[str]] = None,
            headers: t.Optional[list[str]] = None,
    ):
        """TODO: to be defined1. """

        self._origin = origin
        self._methods = methods or self.DEFAULT_METHODS.copy()
        self._headers = headers or self.DEFAULT_HEADERS.copy()

    @property
    def origin(self) -> str:
        """Get the configured origins(s)"""
        return self._origin

    @origin.setter
    def origin(self, value: str):
        if not value:
            raise ValueError("CORS origin cannot be empty")

        self._origin = value

    @property
    def methods(self) -> t.List:
        return self._methods

    @methods.setter
    def methods(self, value: t.Union[str, t.List[str]]):
        if not value:
            raise ValueError("CORS methods cannot be empty")

        if isinstance(value, str):
            value = ",".split(value)
        self._methods = value

    @property
    def headers(self) -> t.List:
        return self._headers
    @headers.setter
    def headers(self, value: t.Union[str, t.List[str]]):
        if not value:
            raise ValueError("CORS headers cannot be empty")

        if isinstance(value, str):
            value = ",".split(value)

        self._headers = value

    def _methods_to_string(self) -> str:
        _methods = set()
        for method in self.methods:
            if isinstance(method, str):
                _methods.add(method.upper())
            if isinstance(method, BaseMethod):
                _methods.add(method.verb)
        return ",".join(method.verb for method in self.methods)

    def set(self, response) -> None:
        response.headers.set("Access-Control-Allow-Origin", self.origin)

        response.headers.add(
            "Access-Control-Allow-Methods", ",".join(self.methods)
        )

        response.headers.add(
            "Access-Control-Allow-Headers",
            # Expects string in following format
            # 'Content-Type, Authorization'
            ",".join(self.headers),
        )
