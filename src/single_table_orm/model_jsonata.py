from contextlib import contextmanager
import string
from typing import Self
from . import connection
from .models import Model


class JsonataFormatter:
    formatter = string.Formatter()

    @contextmanager
    def with_model(self, model: Model):
        """
        Swap model to be used for current formatter
        """
        # get model fields
        self.jsonata_values = {"table_name": "$table_name"}
        for name, _ in model._fields.items():
            self.jsonata_values[name] = getattr(model, name)
            setattr(model, name, f"{{{name}}}")
        self.model = model
        with connection.table.table_context(table_name=f"{{table_name}}"):
            yield self

    @staticmethod
    def from_class(model_class, **kwargs) -> Self:
        """
        Convert a class to JSONata by replacing all fields with python
        format strings ("{field_name}"), and storing the data to be filled.
        """

        data = {}
        for name, _ in model_class._fields.items():
            data[name] = f"{{{name}}}"
        model = model_class(**data)
        return JsonataFormatter(model, kwargs)

    def convert_string(self, formatterstring: str, replacements: dict[str, str]) -> str:
        """
        Convert a string with python format fields to a JSONata string
        by parsing the format string and joining the pieces in JSONata format.
        """

        tokens: list[tuple] = list(self.formatter.parse(formatterstring))
        if len(tokens) == 1 and tokens[0][1] is None:
            # no replacement fields
            return formatterstring
        pieces = []
        for token in tokens:
            # first entry is the prefix before the replacement field
            if token[0] != "":
                pieces.append(f"'{token[0]}'")
            # second entry is the replacement field name
            if token[1] is not None:
                pieces.append(replacements[token[1]])
        # jsonata string concatenate
        return f"{{ % {' & '.join(pieces)} % }}"

    def load(self, data: dict) -> dict:
        """
        Format an object to JSONata by replacing all fields with python.
        Used for formatting database API requests.
        """
        assert self.jsonata_values is not None, (
            "Model must be converted to JSONata first"
        )

        formatted_data = {}
        for key, value in data.items():
            new_value = value
            if isinstance(value, dict):
                new_value = self.load(value)
            elif isinstance(value, list):
                new_value = []
                for item in value:
                    new_value.append(self.load(self.model, item))
            elif isinstance(value, str):
                new_value = self.convert_string(value, self.jsonata_values)
            formatted_data[key] = new_value

        return formatted_data 