"""Explicit JSON serialization; runtime objects never become public metadata."""

import math
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any


def serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return serialize(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: serialize(getattr(value, item.name))
            for item in fields(value)
            if item.metadata.get("serialize", True)
        }
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Cannot serialize {type(value).__name__}")
