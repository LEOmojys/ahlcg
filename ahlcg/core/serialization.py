"""One single place that turns engine objects into JSON-ready data.

The web layer and the tests both rely on this, so a field added to a dataclass
shows up everywhere at once instead of drifting between engine and UI.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


def to_jsonable(obj: Any) -> Any:
    """Recursively convert engine objects into plain JSON-compatible values."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        data: dict[str, Any] = {"_type": type(obj).__name__}
        for f in dataclasses.fields(obj):
            data[f.name] = to_jsonable(getattr(obj, f.name))
        return data
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, bytes):
        return obj.decode("utf-8", "replace")
    if callable(obj):  # abilities / effects are referenced by name, never inlined
        return getattr(obj, "__qualname__", repr(obj))
    return str(obj)
