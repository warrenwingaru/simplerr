from __future__ import annotations

import typing as t


class Config(dict):
    def __init__(self, defaults: dict = None):
        super().__init__(defaults or {})

    # borrowed from flask
    def from_mapping(
            self, mapping: t.Mapping[str, t.Any] | None = None, **kwargs: t.Any
    ) -> bool:
        """Updates the config like :meth:`update` ignoring tiems with
        non-upper keys.

        :return: Always returns ``True``

        .. versionadded:: 0.19.4
        """
        mappings: dict[str, t.Any] = {}
        if mapping is not None:
            mappings.update(mapping)
        mappings.update(kwargs)
        for k, v in mappings.items():
            if k.isupper():
                self[k] = v
        return True
