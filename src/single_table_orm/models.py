import random
import string
from typing import Self
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
        self.query = f"#{field}"
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


class ModelManager:
    def __init__(self, model):
        self.ts = TypeSerializer()
        self.td = TypeDeserializer()
        self.model = model

    def get_load_query(self, model: "Model") -> None:
        return {
            "TableName": connection.table.table_name,
            "Key": {
                "PK": self.ts.serialize(model.get_pk()),
                "SK": self.ts.serialize(model.get_sk()),
            },
        }

    def get(self, **kwargs):
        model: Model = self.model(**kwargs)
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
        model: Model = self.model(**kwargs)
        model.save(self, allow_override=False)
        return model

    def get_save_query(self, model: "Model", allow_override=True) -> dict:
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

    def get_update_query(self, model: "Model", **kwargs) -> None:
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

    def get_delete_query(self, model: "Model") -> dict:
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

    def get_primary_query(self, **kwargs) -> list["Model"]:
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
        model = self.model(**kwargs)
        query = {
            "TableName": connection.table.table_name,
            "KeyConditionExpression": "PK = :pk",
            "ExpressionAttributeValues": {
                ":pk": self.ts.serialize(model.get_pk()),
            },
        }
        return query

    def using(self, **kwargs) -> "QuerySet":
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
        dct["objects"] = ModelManager(model=None)  # Placeholder, set later

        # Automatically assign ModelManager to the class
        new_class = super().__new__(cls, name, bases, dct)
        new_class.objects = ModelManager(model=new_class)

        return new_class

    def __call__(cls, *args, **kwargs):
        instance = super().__call__(*args, **kwargs)
        # We need to trigger the __set__ methods for provided fields
        for key, value in kwargs.items():
            setattr(instance, key, value)
        return instance


class Model(metaclass=ModelMeta):
    objects: ModelManager

    def __init__(self, *_, **kwargs):
        pass

    class Meta:
        suffix = None

    @classmethod
    def _get_suffix(cls):
        suffix = getattr(cls.Meta, "suffix", None)
        if suffix is None:
            return cls.__name__.upper()
        else:
            return suffix.upper()

    def _is_key_valid(self, keys):
        for key in keys:
            if getattr(self, key) is None:
                return False
        return True

    def _get_key_string(self, keys, with_suffix):
        """
        Get the key string for the given keys.
        """
        suffix = self._get_suffix()
        key_parts = []
        if with_suffix:
            key_parts.append(suffix)
        for key in keys:
            identifier = self._fields[key].identifier
            value = str(getattr(self, key))
            key_parts.append(f"{identifier}#{value}")
        if with_suffix:
            key_parts.append(suffix) # Add suffix at the end for PK/SK

        return "#".join(key_parts)

    def get_pk(self) -> str:
        """
        Get the primary key for the model.
        PK format: Identifier#Value#Identifier#Value#Suffix
        """
        if not self._is_key_valid(self._pk_attributes):
            raise MissingRequiredFields(f"Missing primary key fields: {self._pk_attributes}")
        # PK has suffix at the end
        return self._get_key_string(self._pk_attributes, with_suffix=True)

    def get_sk(self) -> str:
        """
        Get the sort key for the model.
        SK format: Identifier#Value#Identifier#Value
        """
        if not self._is_key_valid(self._sk_attributes):
            raise MissingRequiredFields(f"Missing sort key fields: {self._sk_attributes}")
        # SK does not have suffix
        return self._get_key_string(self._sk_attributes, with_suffix=False)

    def get_gsi1pk(self) -> str | None:
        """
        Get the GSI1PK for the model.
        GSI1PK format: Identifier#Value#Identifier#Value#Suffix
        """
        if not self._gsi_attributes:
            return None
        if not self._is_key_valid(self._gsi_attributes):
            # If GSI keys are not set, it's okay, return None
            return None
        # GSI1PK has suffix at the end
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
        query = self.objects.get_save_query(self, allow_override)
        try:
            connection.table.client.put_item(**query)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ObjectAlreadyExists()
            else:
                raise e

    def update(self, **kwargs) -> None:
        """
        Update the object in the database.
        """
        if not self.is_creatable():
            raise MissingRequiredFields(
                f"Missing required fields: {self._fields.keys() - self.__dict__.keys()}"
            )
        query = self.objects.get_update_query(self, **kwargs)
        try:
            connection.table.client.update_item(**query)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ObjectDoesNotExist()
            else:
                raise e
        # Update the object itself
        for key, value in kwargs.items():
            setattr(self, key, value)

    def delete(self) -> None:
        """
        Delete the object from the database.
        """
        query = self.objects.get_delete_query(self)
        connection.table.client.delete_item(**query)

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
        try:
            return self.get_pk() == value.get_pk() and self.get_sk() == value.get_sk()
        except MissingRequiredFields:
            # If keys are missing, they can't be equal
            return False


class QuerySet:
    def __init__(self, model):
        self.model = model
        self._filters = {}
        self._index_name = None
        self._limit = None
        self._exclusive_start_key = None
        self._strong_read = False
        self._reverse_scan = False
        self._only_fields = None

        # Keep track of the query execution
        self._executed = False
        self._results_cache = None
        self._current_page = []
        self._page_index = 0
        self.last_evaluated_key = None

        # Type serializers
        self.ts = TypeSerializer()
        self.td = TypeDeserializer()

    def using(self, **kwargs) -> Self:
        """
        Use the provided values to query the database.

        Initiates the queryset, forcing the start of the query.
        """
        self._filters.update(kwargs)
        return self

    def use_index(self, use: bool) -> Self:
        """
        Use the GSI1 index for the query.
        """
        self._index_name = "GSI1" if use else None
        return self

    def consistent(self, strongly: bool) -> Self:
        """
        Use strongly consistent reads for the query.
        """
        self._strong_read = strongly
        return self

    def limit(self, limit: int) -> Self:
        """
        Limit the number of results returned by the query.
        """
        self._limit = limit
        return self

    def reverse(self) -> Self:
        """
        Reverse the order of the results.
        """
        self._reverse_scan = True
        return self

    def only(self, *fields: str) -> Self:
        """
        Return only the specified fields.
        """
        self._only_fields = fields
        return self

    def starting_after(self, start_after: bool) -> Self:
        """
        Start the query after the given key.

        Must be the LastEvaluatedKey of a previous query.
        """
        self._exclusive_start_key = start_after
        return self

    def get_query(self):
        """
        Get the query parameters for the Query operation.
        """
        query_model = self.model(**self._filters)
        if self._index_name == "GSI1":
            pk_value = query_model.get_gsi1pk()
            if pk_value is None:
                raise ValueError("Cannot query GSI1 without GSI fields.")
            query = {
                "TableName": connection.table.table_name,
                "IndexName": "GSI1",
                "KeyConditionExpression": "GSI1PK = :gsi1pk",
                "ExpressionAttributeValues": {
                    ":gsi1pk": self.ts.serialize(pk_value),
                },
            }
        else:
            pk_value = query_model.get_pk()
            query = {
                "TableName": connection.table.table_name,
                "KeyConditionExpression": "PK = :pk",
                "ExpressionAttributeValues": {
                    ":pk": self.ts.serialize(pk_value),
                },
            }

        # Optional parameters
        if self._limit is not None:
            query["Limit"] = self._limit
        if self._strong_read:
            query["ConsistentRead"] = True
        if self._reverse_scan:
            query["ScanIndexForward"] = False
        if self._exclusive_start_key is not None:
            query["ExclusiveStartKey"] = self._exclusive_start_key
        if self._only_fields is not None:
            query["ProjectionExpression"] = ", ".join([f"#{f}" for f in self._only_fields])
            query["ExpressionAttributeNames"] = {
                f"#{f}": f for f in self._only_fields
            }

        return query

    def __iter__(self):
        if self._results_cache is not None:
            # If already executed, return the cached results
            return iter(self._results_cache)

        # Reset pagination state for new iteration
        self._page_index = 0
        self._current_page = []
        self.last_evaluated_key = None
        self._results_cache = []  # Start building the cache
        return self

    def __next__(self):
        # If we have items left in the current page buffer, return the next one
        if self._page_index < len(self._current_page):
            item = self._current_page[self._page_index]
            self._page_index += 1
            self._results_cache.append(item)  # Add to cache
            return item

        # If the last query indicated no more pages, stop iteration
        if self._executed and self.last_evaluated_key is None:
            raise StopIteration

        # Fetch the next page
        self._current_page = self._fetch_next_page()
        self._page_index = 0

        # If the new page is empty, stop iteration
        if not self._current_page:
            raise StopIteration

        # Return the first item of the new page
        item = self._current_page[self._page_index]
        self._page_index += 1
        self._results_cache.append(item)  # Add to cache
        return item

    def _fetch_next_page(self) -> list:
        """
        Fetches the next page of results from DynamoDB.
        """
        query = self.get_query()
        if self.last_evaluated_key:
            query["ExclusiveStartKey"] = self.last_evaluated_key

        result = connection.table.client.query(**query)
        self._executed = True
        self.last_evaluated_key = result.get("LastEvaluatedKey")

        items = []
        for item_data in result.get("Items", []):
            # Deserialize item data
            deserialized_data = {
                k: self.td.deserialize(v) for k, v in item_data.items()
            }
            # Create model instance, skipping __init__ logic that might re-validate
            instance = self.model.__new__(self.model)
            instance.__dict__.update(deserialized_data)
            items.append(instance)

        return items 