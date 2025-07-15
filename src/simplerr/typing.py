import typing as t

if t.TYPE_CHECKING:
    from werkzeug.datastructures import Headers
    from werkzeug.wrappers import Response

ResponseValue = t.Union[
    "Response",
    str,
    dict[str, t.Any]
]

HeaderValue = t.Union[
    str,
    t.List[str],
    t.Tuple[str, ...],
]

HeadersValue = t.Union[
    "Headers",
    t.Mapping[str, HeaderValue],
    t.Sequence[t.Tuple[str, HeaderValue]],
]

ResponseReturnValue = t.Union[
    ResponseValue,
    t.Tuple[ResponseValue, HeadersValue],
    t.Tuple[ResponseValue, int],
    t.Tuple[ResponseValue, int, HeadersValue],
]

ResponseClass = t.TypeVar("ResponseClass", bound="Response")