from __future__ import annotations

import json
import os
import typing as t


class Config(dict):
    def __init__(self, defaults: t.Optional[dict[str, t.Any]] = None):
        super().__init__(defaults or {})

    def from_prefixed_env(
            self, prefix: str = "SIMPLERR", *, loads: t.Callable[[str], t.Any] = json.loads
    ):
        prefix = f"{prefix}_"

        for key in sorted(os.environ):
            if not key.startswith(prefix):
                continue

            value = os.environ[key]
            key = key.removeprefix(prefix)

            try:
                value = loads(value)
            except Exception:
                pass

            if "__" not in key:
                # A non-nested key, set directly.
                self[key] = value
                continue

            current = self
            *parts, tail = key.split("__")

            for part in parts:
                # if an intermediate dict does not exist, create a new dict
                if part not in current:
                    current[part] = {}

                current = current[part]

            current[tail] = value

        return True

    def from_mapping(self, mapping: t.Optional[t.Mapping[str, t.Any]] = None, **kwargs: t.Any):
        mappings: dict[str, t.Any] = {}
        mappings.update(kwargs)

        if mapping is not None:
            mappings.update(mapping)
        mappings.update(kwargs)
        for key, value in mappings.items():
            if key.isupper():
                self[key] = value

        return True

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {dict.__repr__(self)}>"
