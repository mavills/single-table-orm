from __future__ import annotations

from typing import (
    Any,
    Generic,
    Optional,
    TypeVar,
    overload,
)

from pydantic import ValidationError


T = TypeVar("T")  # the "real" value that lives in the field


class Field(Generic[T]):
    def __init__(
        self,
        field_type: type[Any],
        *,
        pk: bool = False,
        sk: bool = False,
        gsi: bool = False,
        identifier: Optional[str] = None,
    ) -> None:
        """
        A field descriptor for use in models.

        Args:
            field_type: The type of the field.
            pk: If the field is part of the primary key.
            sk: If the field is part of the sort key.
            gsi: If the field is part of a global secondary index.
            identifier: A string that is used in keys to identify the field.
            Defaults to the first letter in uppercase.
        """
        self.field_type = field_type
        self.pk = pk
        self.sk = sk
        self.gsi = gsi
        self.identifier = identifier
        self.name: Optional[str] = None  # Will be set dynamically in the metaclass

    def __set_name__(self, owner: type[Any], name: str) -> None:  # noqa: D401
        if self.identifier is None:
            self.identifier = name[0].upper()
        self.name = name

    # --------- the key part ---------
    @overload
    def __get__(self, instance: None, owner: type[Any]) -> "Field[T]": ...
    @overload
    def __get__(self, instance: Any, owner: type[Any]) -> T: ...

    # --------------------------------

    def __get__(self, instance, owner):
        if instance is None:  # access through the class
            return self
        return instance.__dict__.get(self.name)  # type: ignore[arg-type]

    def __set__(self, instance, value: Optional[T]) -> None:  # type: ignore[override]
        if value is not None:
            try:
                self.field_type(value)
            except (TypeError, ValidationError) as exc:
                raise TypeError(
                    f"Invalid value for field '{self.name}': {exc}"
                ) from exc
        instance.__dict__[self.name] = value
