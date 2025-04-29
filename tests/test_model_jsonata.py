from tests.utils import local_client # Updated import
from single_table_orm.fields import Field # Updated import
from single_table_orm.model_jsonata import JsonataFormatter # Updated import
from single_table_orm.models import Model # Updated import


class DummyModel(Model):
    a_pk = Field(str, pk=True)
    b_sk = Field(str, sk=True)
    c_gsi1pk = Field(str, gsi=True)

    class Meta:
        suffix = "DummyModel"


def test_save(local_client):
    model = DummyModel(a_pk="a", b_sk="b", c_gsi1pk="c")

    with JsonataFormatter().with_model(model) as f:
        query = f.load(model.objects.get_save_query(model, allow_override=True))
    assert query == {
        "Item": {
            "GSI1PK": {
                "S": "{ % 'DummyModel#' & c & '#DummyModel' % }", # Updated format
            },
            "PK": {
                "S": "{ % 'DummyModel#' & a & '#DummyModel' % }", # Updated format
            },
            "SK": {
                "S": "{ % 'B#' & b % }", # Updated format (no suffix)
            },
            "a_pk": {
                "S": "{ % a % }",
            },
            "b_sk": {
                "S": "{ % b % }",
            },
            "c_gsi1pk": {
                "S": "{ % c % }",
            },
        },
        "TableName": "{ % $table_name % }",
    }


def test_get(local_client):
    model = DummyModel(a_pk="a", b_sk="b", c_gsi1pk="c")

    with JsonataFormatter().with_model(model) as f:
        query = f.load(model.objects.get_load_query(model))
    assert query == {
        "Key": {
            "PK": {
                "S": "{ % 'DummyModel#' & a & '#DummyModel' % }", # Updated format
            },
            "SK": {
                "S": "{ % 'B#' & b % }", # Updated format
            },
        },
        "TableName": "{ % $table_name % }",
    }


def test_delete(local_client):
    model = DummyModel(a_pk="a", b_sk="b", c_gsi1pk="c")

    with JsonataFormatter().with_model(model) as f:
        query = f.load(model.objects.get_delete_query(model))
    assert query == {
        "Key": {
            "PK": {
                "S": "{ % 'DummyModel#' & a & '#DummyModel' % }", # Updated format
            },
            "SK": {
                "S": "{ % 'B#' & b % }", # Updated format
            },
        },
        "TableName": "{ % $table_name % }",
    }


def test_query(local_client):
    model = DummyModel(a_pk="a", b_sk="b", c_gsi1pk="c")
    with JsonataFormatter().with_model(model) as f:
        # Instantiate QuerySet first
        qs = DummyModel.objects.using(
            a_pk=model.a_pk,
            c_gsi1pk=model.c_gsi1pk # Use GSI for index query
        ).use_index(True) # Specify index usage

        # Apply other options
        qs = qs.limit(1).reverse().starting_after(True).only("a_pk", "b_sk")

        # Get and format the final query
        query = f.load(qs.get_query())

    assert query == {
        "ExpressionAttributeNames": { # Added ExpressionAttributeNames
            "#a_pk": "a_pk",
            "#b_sk": "b_sk"
        },
        "ExpressionAttributeValues": {
            ":gsi1pk": {
                "S": "{ % 'DummyModel#' & c & '#DummyModel' % }", # Updated format for GSI1PK
            },
        },
        "IndexName": "GSI1", # Added IndexName
        "KeyConditionExpression": "GSI1PK = :gsi1pk", # Updated KeyConditionExpression
        "Limit": 1, # Added Limit
        "ProjectionExpression": "#a_pk, #b_sk", # Updated ProjectionExpression with Names
        "ScanIndexForward": False,
        "ExclusiveStartKey": True, # Added ExclusiveStartKey
        "TableName": "{ % $table_name % }",
    } 