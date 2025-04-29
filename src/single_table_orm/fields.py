from pydantic import ValidationError


class Field:
    def __init__(self, field_type, pk=False, sk=False, gsi=False, identifier=None):
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
        self.name = None  # Will be set dynamically in the metaclass

    def __set_name__(self, owner, name: str):
        if self.identifier is None:
            self.identifier = name[0].upper()
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.__dict__.get(self.name)

    def __set__(self, instance, value):
        if value is not None:
            try:
                self.field_type(value)
            except (TypeError, ValidationError) as e:
                raise TypeError(f"Invalid value for field '{self.name}': {e}")
            instance.__dict__[self.name] = value
        else:
            instance.__dict__[self.name] = None 