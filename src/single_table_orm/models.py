import random
import string
from typing import Generic, Self, Type, TypeVar
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer

from . import connection
from .fields import Field
from botocore.exceptions import ClientError


class ObjectDoesNotExist(Exception):
    """Raised when the requested object does not exist."""

    def __init__(self, message="The requested object does not exist."):
        self.message = message
        super().__init__(self.message)


class ObjectAlreadyExists(Exception):
    """Raised when the object already exists."""

    def __init__(self, message="The object already exists."):
        self.message = message
        super().__init__(self.message)


class MissingRequiredFields(Exception):
    """Raised when the object is missing required fields."""

    def __init__(self, message="The object is missing required fields."):
        self.message = message
        super().__init__(self.message)


class F:
    def __init__(self, field: str):
        self.query = f"{field}"
        self.names = {
            f"#{field}": field,
        }
        self.values = {}

    def get_values(self):
        ts = TypeSerializer()
        serialized = {}
        for key, value in self.values.items():
            serialized[key] = ts.serialize(value)
        return serialized

    def __add__(self, other) -> "F":
        if isinstance(other, F):
            self.names.update(other.names)
            self.values.update(other.values)
            self.query = f"{self.query} + {other.query}"
        else:
            subkey = "".join(random.choice(string.ascii_lowercase) for _ in range(10))
            self.values.update({f":{subkey}": other})
            self.query = f"{self.query} + :{subkey}"

        return self


MT = TypeVar("MT", bound="Model")


class ModelManager(Generic[MT]):
    def __init__(self, model: Type[MT]):
        self.ts = TypeSerializer()
        self.td = TypeDeserializer()
        self.model = model

    def get_load_query(self, model: MT) -> None:
        return {
            "TableName": connection.table.table_name,
            "Key": {
                "PK": self.ts.serialize(model.get_pk()),
                "SK": self.ts.serialize(model.get_sk()),
            },
        }

    def get(self, **kwargs) -> MT:
        model: MT = self.model(**kwargs)
        query = self.get_load_query(model)
        result = connection.table.client.get_item(**query)
        # If the item does not exist, the "Item" key will not be present
        if "Item" not in result:
            raise ObjectDoesNotExist()
        for name, _ in model._fields.items():
            setattr(model, name, self.td.deserialize(result["Item"].get(name)))
        return model

    def create(self, **kwargs):
        """
        Explicitly create a new object in the database.
        The object cannot already exist.
        """
        model: MT = self.model(**kwargs)
        model.save(allow_override=False)
        return model

    def get_save_query(self, model: MT, allow_override=True) -> dict:
        """
        Query to save an object to the database.
        Will be used by the PutItem operation.

        Sets:
        - TableName
        - ConditionExpression: If not allowed to override, it should not already exist.
        - Item (all fields + SK and PK)
        """
        # TableName
        put_fields = {
            "TableName": connection.table.table_name,
        }

        # Item
        item = {}
        for name, _ in model._fields.items():
            item[name] = self.ts.serialize(getattr(model, name))
        item["PK"] = self.ts.serialize(model.get_pk())
        item["SK"] = self.ts.serialize(model.get_sk())
        # GSI1PK is allowed to be None
        if model.get_gsi1pk() is not None and "GSI1PK" not in item:
            item["GSI1PK"] = self.ts.serialize(model.get_gsi1pk())
        put_fields["Item"] = item

        # ConditionExpression
        if not allow_override:
            put_fields["ConditionExpression"] = "attribute_not_exists(PK)"

        return put_fields

    def get_update_query(self, model: MT, **kwargs) -> None:
        """
        Query to update an object in the database.

        Sets:
        - TableName
        - Key
        - ConditionExpression
        - UpdateExpression
        - ExpressionAttributeNames
        - ExpressionAttributeValues
        """

        # TableName
        update_query = {
            "TableName": connection.table.table_name,
        }

        # Key
        update_query["Key"] = {
            "PK": self.ts.serialize(model.get_pk()),
            "SK": self.ts.serialize(model.get_sk()),
        }

        # ConditionExpression
        update_query["ConditionExpression"] = "attribute_exists(PK)"

        # UpdateExpression
        update_query["UpdateExpression"] = ""
        update_query["ExpressionAttributeNames"] = {}
        update_query["ExpressionAttributeValues"] = {}
        expressions = []
        for key, value in kwargs.items():
            if isinstance(value, F):
                expressions.append(f"#{key} = {value.query}")
                update_query["ExpressionAttributeNames"].update(value.names)
                update_query["ExpressionAttributeValues"].update(value.get_values())
                continue
            expressions.append(f"#{key} = :{key}")
            update_query["ExpressionAttributeNames"][f"#{key}"] = key
            update_query["ExpressionAttributeValues"][f":{key}"] = self.ts.serialize(
                value
            )
        update_query["UpdateExpression"] = "SET " + ", ".join(expressions)

        return update_query

    def get_delete_query(self, model: MT) -> dict:
        """
        Query to delete an object from the database.
        Will be used by the DeleteItem operation.

        Sets:
        - TableName
        - Key
        """
        return {
            "TableName": connection.table.table_name,
            "Key": {
                "PK": self.ts.serialize(model.get_pk()),
                "SK": self.ts.serialize(model.get_sk()),
            },
        }

    def get_primary_query(self, **kwargs) -> list[MT]:
        """
        Query to get all objects from the database using the default primary keyset.
        Will be used by the Query operation.

        Sets:
        - TableName
        - KeyConditionExpression
        - ExpressionAttributeValues

        Does not set:
        - ConsistentRead
        - ExclusiveStartKey
        - ExpressionAttributeNames
        - FilterExpression
        - IndexName
        - Limit
        - ScanIndexForward
        - Select
        """
        model: MT = self.model(**kwargs)
        query = {
            "TableName": connection.table.table_name,
            "KeyConditionExpression": "PK = :pk",
            "ExpressionAttributeValues": {
                ":pk": self.ts.serialize(model.get_pk()),
            },
        }
        return query

    def using(self, **kwargs) -> "QuerySet[MT]":
        """
        Use the provided values to query the database.

        Initiates the queryset, forcing the start of the query.
        """
        return QuerySet(self.model).using(**kwargs)


class ModelMeta(type):
    def __new__(cls, name, bases, dct):
        fields = {}
        pk_attributes = []
        sk_attributes = []
        gsi_attributes = []
        for key, value in dct.items():
            if isinstance(value, Field):
                fields[key] = value
                if value.pk:
                    pk_attributes.append(key)
                if value.sk:
                    sk_attributes.append(key)
                if value.gsi:
                    gsi_attributes.append(key)
        dct["_fields"] = fields  # Store fields metadata
        dct["_pk_attributes"] = pk_attributes
        dct["_sk_attributes"] = sk_attributes
        dct["_gsi_attributes"] = gsi_attributes
        if "objects" not in dct:
            dct["objects"] = ModelManager(model=None)  # Placeholder, update later

        # Automatically assign ModelManager to the class
        new_class = super().__new__(cls, name, bases, dct)
        # link the manager to the model class
        new_class.objects = ModelManager(model=new_class)

        return new_class

    def __call__(cls, *args, **kwargs):
        instance = super().__call__(*args, **kwargs)
        # We need to trigger the __set__ methods for provided fields
        for key, value in kwargs.items():
            setattr(instance, key, value)
        return instance


class Model(metaclass=ModelMeta):
    objects: ModelManager[Self]

    def __init__(self, *_, **kwargs):
        pass

    class Meta:
        suffix = None

    @classmethod
    def _get_suffix(cls):
        """
        Get the suffix that appears after the primary key in the key string.
        """
        if cls.Meta.suffix:
            return cls.Meta.suffix
        return cls.__name__

    def _is_key_valid(self, keys):
        """
        Check if all keys are set.
        """
        return all(getattr(self, key) is not None for key in keys)

    def _get_key_string(self, keys, with_suffix):
        """
        Get the key string for the given keys.
        Append suffix to the key string if with_suffix is True.
        """
        result = []
        for key in keys:
            field: Field = self._fields[key]
            result.append(field.identifier)
            result.append(getattr(self, key))
        return "#".join(
            [r for r in result if r] + ([self._get_suffix()] if with_suffix else [])
        )

    def get_pk(self) -> str:
        """
        Get the partition key string.
        """
        if not self._is_key_valid(self._pk_attributes):
            raise ValueError("Partition key is not valid.", self._pk_attributes)
        return self._get_key_string(self._pk_attributes, with_suffix=True)

    def get_sk(self) -> str:
        """
        Get the sort key string.
        """
        if not self._is_key_valid(self._sk_attributes):
            raise ValueError("Sort key is not valid.", self._sk_attributes)
        return self._get_key_string(self._sk_attributes, with_suffix=False)

    def get_gsi1pk(self) -> str | None:
        """
        Get the GSI1 partition key string.
        """
        if len(self._gsi_attributes) == 0:
            return None
        if not self._is_key_valid(self._gsi_attributes):
            raise ValueError("GSI key is not valid.", self._gsi_attributes)
        return self._get_key_string(self._gsi_attributes, with_suffix=True)

    def save(self, allow_override=True) -> None:
        """
        Save the object to the database.

        By default, this will override any existing object with the same keys.
        If you want to prevent this, set `allow_override` to False.
        """
        if not self.is_creatable():
            raise MissingRequiredFields(
                f"Missing required fields: {self._fields.keys() - self.__dict__.keys()}"
            )
        put_fields = self.objects.get_save_query(self, allow_override)
        try:
            _ = connection.table.client.put_item(**put_fields)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                if not allow_override:
                    raise ObjectAlreadyExists()
            raise

    def update(self, **kwargs) -> None:
        """
        Update the object in the database.
        """
        update_query = self.objects.get_update_query(self, **kwargs)
        try:
            _ = connection.table.client.update_item(**update_query)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ObjectDoesNotExist()
            raise

    def delete(self) -> None:
        """
        Delete the object from the database.
        """
        delete_query = self.objects.get_delete_query(self)
        connection.table.client.delete_item(**delete_query)

    def is_creatable(self):
        """
        Check if the model has all required fields to be created.

        Checks:
        - All PK fields are set
        - All SK fields are set
        - All GSI fields are set
        - All fields are set
        """
        try:
            self.get_pk()
            self.get_sk()
            self.get_gsi1pk()
        except MissingRequiredFields:
            return False

        for name in self._fields.keys():
            if name not in self.__dict__:
                return False
        return True

    def to_json(self):
        """
        Convert the model to a JSON object.
        """
        return {name: getattr(self, name) for name in self._fields.keys()}

    def __eq__(self, value):
        """
        Compare two models for equality.

        Two models are considered equal if they have the same type and PK/SK.
        """
        if not isinstance(value, self.__class__):
            return False
        return all(
            getattr(self, name) == getattr(value, name) for name in self._fields.keys()
        )


class QuerySet(Generic[MT]):
    def __init__(self, model: Type[MT]):
        self.ts = TypeSerializer()
        self.td = TypeDeserializer()

        self.model = model

        # Query building
        self._using: MT = None
        self._use_index = False
        self._consistent = False
        self._starting_after = False
        # Pagination limit (external)
        self._limit = None
        # Limit the number of items on a single page returned by the API.
        self._internal_limit = None
        self._reverse = False
        self._only = None

        # Query evaluation
        self._last_page = False
        self._last_evaluated = None
        self._current_page_data = []
        self._current_item_on_page = 0
        self._evaluated_query = None

    def using(self, **kwargs) -> "QuerySet[MT]":
        """
        Use the provided values to query the database.

        Initiates the queryset, forcing the start of the query.

        Example:
        ```python
        queryset = TestModel.objects.using(a_pk="aaa", b_sk="bbb")
        ```
        """
        self._using = self.model(**kwargs)
        return self

    def use_index(self, use: bool) -> Self:
        """
        Query the secondary index instead of the primary key.
        """
        self._use_index = use
        return self

    def consistent(self, strongly: bool) -> Self:
        """
        Use strongly consistent reads.
        """
        self._consistent = strongly
        return self

    def limit(self, limit: int) -> Self:
        """
        Limit the number of items returned by the queryset.
        """
        self._limit = limit
        return self

    def reverse(self) -> Self:
        """
        Set the order of the queryset to descending
        """
        self._reverse = True
        return self

    def only(self, *fields: str) -> Self:
        """
        Only return the specified fields from the queryset.
        """
        self._only = fields
        return self

    def starting_after(self, start_after: bool) -> Self:
        """
        Updates the queryset to only start after the SK of the provided object.

        This is useful for external pagination, where the client provides the last item.
        Internal pagination is handled automatically using LastEvaluatedKey and ExclusiveStartKey.
        """
        self._starting_after = start_after
        return self

    def get_query(self):
        """
        Get the Query API operation parameters.
        """
        query = {
            "TableName": connection.table.table_name,
        }
        if not self._use_index:
            query["KeyConditionExpression"] = "PK = :pk"
            query["ExpressionAttributeValues"] = {
                ":pk": self.ts.serialize(self._using.get_pk()),
            }
        else:
            query["IndexName"] = "GSI-1"
            query["KeyConditionExpression"] = "GSI1PK = :gsi1pk"
            query["ExpressionAttributeValues"] = {
                ":gsi1pk": self.ts.serialize(self._using.get_gsi1pk()),
            }
        if self._starting_after:
            query["KeyConditionExpression"] += " AND SK > :sk"
            query["ExpressionAttributeValues"][":sk"] = self.ts.serialize(
                self._using.get_sk()
            )
        if self._consistent:
            query["ConsistentRead"] = True
        if self._internal_limit:
            query["Limit"] = self._internal_limit
        if self._reverse:
            query["ScanIndexForward"] = False
        if self._only:
            query["ProjectionExpression"] = ", ".join(self._only)

        return query

    def __iter__(self):
        """
        Initializes the iteration and returns the iterator object.
        """
        self._last_page = False
        self._last_evaluated = None
        self._current_page_data = []
        self._current_item_on_page = 0
        self._total_items = 0
        self._evaluated_query = self.get_query()
        return self

    def __next__(self):
        """
        Fetches the next item from the queryset. Handles pagination under the hood.
        """
        # Check if the requested limit has been reached
        if self._limit is not None and self._total_items >= self._limit:

            raise StopIteration
        # Load the next page if no data available, or if the current page is exhausted
        if self._current_item_on_page >= len(self._current_page_data):
            if self._last_page:
                raise StopIteration
            # Set page data and reset the item counter
            self._current_page_data = self._fetch_next_page()
            self._current_item_on_page = 0

        # If no more data is available, stop iteration
        if len(self._current_page_data) == 0:
            raise StopIteration

        # Return the next item
        item = self._current_page_data[self._current_item_on_page]
        self._current_item_on_page += 1
        self._total_items += 1
        return self.model(**item)

    def _fetch_next_page(self) -> list:
        """
        Fetch the next page of the query using the LastEvaluatedKey if available.
        """
        # Set the ExclusiveStartKey if available
        if self._last_evaluated is not None:
            self._evaluated_query["ExclusiveStartKey"] = self._last_evaluated
        else:
            self._evaluated_query.pop("ExclusiveStartKey", None)

        # Query the database
        self._response = connection.table.client.query(**self._evaluated_query)

        # Load last evaluated key
        if "LastEvaluatedKey" in self._response:
            self._last_evaluated = self._response["LastEvaluatedKey"]
        else:
            self._last_evaluated = None
            self._last_page = True
        items = self._response.get("Items", [])
        return [
            {key: self.td.deserialize(value) for key, value in item.items()}
            for item in items
        ]
