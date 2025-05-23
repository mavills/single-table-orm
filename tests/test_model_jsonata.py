from single_table_orm.fields import Field
from single_table_orm.model_jsonata import JsonataFormatter
from single_table_orm.models import Model
from tests.utils import mock_table as local_client


class DummyModel(Model):
    a_pk = Field(str, pk=True)
    b_sk = Field(str, sk=True)
    c_gsi1pk = Field(str, gsi=True)


def test_save(local_client):
    model = DummyModel(a_pk="a", b_sk="b", c_gsi1pk="c")

    with JsonataFormatter().with_model(model) as f:
        query = f.load(model.objects.get_save_query(model, allow_override=True))
    assert query == {
        "Item": {
            "GSI1PK": {
                "S": "{ % 'C#' & c & '#DummyModel' % }",
            },
            "PK": {
                "S": "{ % 'A#' & a & '#DummyModel' % }",
            },
            "SK": {
                "S": "{ % 'B#' & b % }",
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
                "S": "{ % 'A#' & a & '#DummyModel' % }",
            },
            "SK": {
                "S": "{ % 'B#' & b % }",
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
                "S": "{ % 'A#' & a & '#DummyModel' % }",
            },
            "SK": {
                "S": "{ % 'B#' & b % }",
            },
        },
        "TableName": "{ % $table_name % }",
    }


def test_query(local_client):
    model = DummyModel(a_pk="a", b_sk="b", c_gsi1pk="c")
    with JsonataFormatter().with_model(model) as f:
        query = f.load(
            DummyModel.objects.using(
                a_pk=model.a_pk, b_sk=model.b_sk, c_gsi1pk=model.c_gsi1pk
            )
            .limit(1)
            .reverse()
            .starting_after(True)
            .only("a_pk", "b_sk")
            .get_query()
        )
    assert query == {
        "ExpressionAttributeValues": {
            ":pk": {
                "S": "{ % 'A#' & a & '#DummyModel' % }",
            },
            ":sk": {
                "S": "{ % 'B#' & b % }",
            },
        },
        "KeyConditionExpression": "PK = :pk AND SK > :sk",
        "ProjectionExpression": "a_pk, b_sk",
        "ScanIndexForward": False,
        "TableName": "{ % $table_name % }",
    }
