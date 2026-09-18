"""Public command metadata and results shared with the TailCloud interface."""

from dataclasses import dataclass, field
import keyword
import re
from typing import Any, Callable, Literal

from .errors import ValidationError

FieldValue = str | int | bool
FieldType = Literal["str", "int", "bool"]
Status = Literal["OK", "ERROR", "WARNING"]
Color = Literal["Primary", "Red", "Gray"]


@dataclass(frozen=True)
class Result:
    title: str
    description: str | None = None
    status: Status = "OK"
    button: str | None = None
    data: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Result title must be a non-empty string")
        if self.status not in ("OK", "ERROR", "WARNING"):
            raise ValueError("Unsupported result status")


@dataclass(frozen=True)
class Field:
    id: str
    name: str
    type: FieldType = "str"
    description: str | None = None
    required: bool = False
    default: FieldValue | None = None
    choices: tuple[FieldValue, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    secret: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.isidentifier() or keyword.iskeyword(self.id):
            raise ValueError("Field id must be a valid Python parameter name")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Field name must be a non-empty string")
        if self.type not in ("str", "int", "bool"):
            raise ValueError("Unsupported field type")
        object.__setattr__(self, "choices", tuple(self.choices))
        for bound in (self.minimum, self.maximum):
            if bound is not None and (self.type != "int" or type(bound) is not int):
                raise ValueError("Bounds are only supported for integer fields")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Minimum cannot exceed maximum")
        for choice in self.choices:
            self.validate(choice)
        if self.default is not None:
            self.validate(self.default)

    def validate(self, value: Any) -> FieldValue:
        """Validate strictly: JSON booleans are not integers, strings are not coerced."""
        expected = {"str": str, "int": int, "bool": bool}[self.type]
        if type(value) is not expected:
            raise ValidationError(f"Field '{self.id}' must have type {self.type}")
        if self.required and isinstance(value, str) and not value.strip():
            raise ValidationError(f"Field '{self.id}' cannot be empty")
        if self.choices and value not in self.choices:
            raise ValidationError(f"Field '{self.id}' must match one of its choices")
        if self.minimum is not None and value < self.minimum:
            raise ValidationError(f"Field '{self.id}' must be >= {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ValidationError(f"Field '{self.id}' must be <= {self.maximum}")
        return value


@dataclass(frozen=True)
class Command:
    id: str
    title: str
    color: Color = "Primary"
    description: str | None = None
    fields: tuple[Field, ...] = ()
    func: Callable[..., Result | None] | None = field(
        default=None, repr=False, compare=False, metadata={"serialize": False}
    )

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", self.id):
            raise ValueError("Command id must be a non-empty identifier")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Command title must be a non-empty string")
        if self.color not in ("Primary", "Red", "Gray"):
            raise ValueError("Unsupported command color")
        object.__setattr__(self, "fields", tuple(self.fields))
        if any(not isinstance(item, Field) for item in self.fields):
            raise TypeError("Command fields must be Field instances")
        if len({item.id for item in self.fields}) != len(self.fields):
            raise ValueError("Field ids must be unique within a command")
