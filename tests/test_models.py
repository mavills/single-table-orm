import pytest
from tests.utils import mock_table
from single_table_orm.fields import Field
from single_table_orm.models import F, Model, ObjectAlreadyExists, ObjectDoesNotExist
from single_table_orm.connection import table  # Updated import


def test_partition_key_generation():
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_pk = Field(str, pk=True)
        c_sk = Field(str, sk=True)
        d_sk = Field(str, sk=True)
        e_gsi = Field(str, gsi=True)
        f_gsi = Field(str, gsi=True)
        another_attribute = Field(str, pk=False)

    model = TestModel(
        a_pk="aaa",
        b_pk="bbb",
        c_sk="ccc",
        d_sk="ddd",
        e_gsi="eee",
        f_gsi="fff",
        another_attribute="another",
    )

    assert model.get_pk() == "A#aaa#B#bbb#TestModel"
    assert model.get_sk() == "C#ccc#D#ddd"
    assert model.get_gsi1pk() == "E#eee#F#fff#TestModel"


def test_key_generation_changed_suffix():
    class TestModel(Model):
        value_1 = Field(str, pk=True)
        value_2 = Field(str, sk=True)
        value_3 = Field(str, gsi=True)
        another_attribute = Field(str)

        class Meta:
            suffix = "ChangedSuffix"

    model = TestModel(
        value_1="value_1",
        value_2="value_2",
        value_3="value_3",
        another_attribute="another",
    )

    assert model.get_pk() == "V#value_1#ChangedSuffix"
    assert model.get_sk() == "V#value_2"
    assert model.get_gsi1pk() == "V#value_3#ChangedSuffix"


def test_is_key_valid():
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_pk = Field(str, sk=True)
        c_sk = Field(str, gsi=True)
        another_attribute = Field(str)

    model = TestModel(
        a_pk=None,
        b_sk=None,
        c_gsi1pk=None,
        another_attribute="another",
    )

    with pytest.raises(ValueError):
        model.get_pk()

    with pytest.raises(ValueError):
        model.get_sk()

    with pytest.raises(ValueError):
        model.get_gsi1pk()


def test_model_get_exists(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
    )

    mock_table.put_item(
        TableName=table.table_name,
        Item={
            "PK": {"S": model.get_pk()},
            "SK": {"S": model.get_sk()},
            "a_pk": {"S": model.a_pk},
            "b_sk": {"S": model.b_sk},
            "another_attribute": {"S": model.another_attribute},
        },
    )

    retrieved_model = TestModel.objects.get(a_pk="aaa", b_sk="bbb")

    assert retrieved_model.a_pk == "aaa"
    assert retrieved_model.b_sk == "bbb"
    assert retrieved_model.another_attribute == "another"


def test_model_get_does_not_exist(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

    # Do not create anything

    with pytest.raises(ObjectDoesNotExist):
        TestModel.objects.get(a_pk="aaa", b_sk="bbb")


def test_save(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
    )
    model.save()

    result = mock_table.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model.get_pk()},
            "SK": {"S": model.get_sk()},
        },
    )
    assert "Item" in result
    assert result["Item"] == {
        "PK": {
            "S": "A#aaa#TestModel",
        },
        "SK": {
            "S": "B#bbb",
        },
        "a_pk": {
            "S": "aaa",
        },
        "another_attribute": {
            "S": "another",
        },
        "b_sk": {
            "S": "bbb",
        },
    }


def test_save_allow_override(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

    model_1 = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
    )
    model_1.save()

    model_2 = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="more",
    )

    model_2.save(allow_override=True)

    result = mock_table.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model_2.get_pk()},
            "SK": {"S": model_2.get_sk()},
        },
    )
    assert model_1.get_pk() == model_2.get_pk()
    assert model_1.get_sk() == model_2.get_sk()

    assert "Item" in result
    assert result["Item"] == {
        "PK": {
            "S": "A#aaa#TestModel",
        },
        "SK": {
            "S": "B#bbb",
        },
        "a_pk": {
            "S": "aaa",
        },
        "another_attribute": {
            # This attribute was overwritten by .save()
            "S": "more",
        },
        "b_sk": {
            "S": "bbb",
        },
    }


def test_save_prevent_override(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

    model_1 = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
    )
    model_1.save()

    model_2 = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="more",
    )

    assert model_1.get_pk() == model_2.get_pk()
    assert model_1.get_sk() == model_2.get_sk()
    with pytest.raises(ObjectAlreadyExists):
        model_2.save(allow_override=False)

def test_model_typing(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute: Field[dict] = Field(dict)

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute={"a": "b"},
    )
    model.save()
    assert model.a_pk == "aaa"
    assert model.b_sk == "bbb"
    assert model.another_attribute == {"a": "b"}
    assert type(model.another_attribute) == dict
    assert type(TestModel.another_attribute) == Field


def test_delete(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
    )
    mock_table.put_item(
        TableName=table.table_name,
        Item={
            "PK": {"S": model.get_pk()},
            "SK": {"S": model.get_sk()},
            "a_pk": {"S": model.a_pk},
            "b_sk": {"S": model.b_sk},
            "another_attribute": {"S": model.another_attribute},
        },
    )
    model.delete()

    result = mock_table.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model.get_pk()},
            "SK": {"S": model.get_sk()},
        },
    )
    assert "Item" not in result


def test_update(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)
        updating_attribute = Field(str)

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
        updating_attribute="updating",
    )

    model.save()
    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
    )

    model.update(updating_attribute="updated")

    result = mock_table.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model.get_pk()},
            "SK": {"S": model.get_sk()},
        },
    )
    assert "Item" in result
    assert result["Item"] == {
        "PK": {
            "S": "A#aaa#TestModel",
        },
        "SK": {
            "S": "B#bbb",
        },
        "a_pk": {
            "S": "aaa",
        },
        "b_sk": {
            "S": "bbb",
        },
        "another_attribute": {
            "S": "another",
        },
        "updating_attribute": {
            "S": "updated",
        },
    }


def test_update_using_expression(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)
        updating_attribute = Field(int)

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
        updating_attribute=1,
    )
    model.save()

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
    )

    model.update(updating_attribute=F("updating_attribute") + 1)

    result = mock_table.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model.get_pk()},
            "SK": {"S": model.get_sk()},
        },
    )
    assert "Item" in result
    assert result["Item"] == {
        "PK": {
            "S": "A#aaa#TestModel",
        },
        "SK": {
            "S": "B#bbb",
        },
        "a_pk": {
            "S": "aaa",
        },
        "another_attribute": {
            "S": "another",
        },
        "updating_attribute": {
            "N": "2",
        },
        "b_sk": {
            "S": "bbb",
        },
    }


def test_query(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)

    model_1 = TestModel(
        a_pk="aaa",
        b_sk="bbb",
    )
    model_1.save()

    model_2 = TestModel(
        a_pk="aaa",
        b_sk="ccc",
    )
    model_2.save()

    queryset = TestModel.objects.using(a_pk="aaa")
    models = list(queryset)

    assert len(models) == 2
    # Models will be sorted by SK
    assert model_1 == models[0]
    assert model_2 == models[1]


def test_query_limit(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)

    model_1 = TestModel(
        a_pk="aaa",
        b_sk="bbb",
    )
    model_1.save()

    model_2 = TestModel(
        a_pk="aaa",
        b_sk="ccc",
    )
    model_2.save()

    queryset = TestModel.objects.using(a_pk="aaa").limit(1)
    models = list(queryset)

    assert len(models) == 1
    # Models will be sorted by SK
    assert model_1 == models[0]


def test_query_limit_starting_after(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)

    model_1 = TestModel(
        a_pk="aaa",
        b_sk="bbb",
    )
    model_1.save()

    model_2 = TestModel(
        a_pk="aaa",
        b_sk="ccc",
    )
    model_2.save()

    queryset = (
        TestModel.objects.using(a_pk="aaa", b_sk="bbb").starting_after(True).limit(1)
    )
    models = list(queryset)

    assert len(models) == 1
    # Models will be sorted by SK
    assert model_2 == models[0]


def test_query_use_index(mock_table):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        c_gsi1pk = Field(str, gsi=True)

    model_1 = TestModel(
        a_pk="xxx",
        b_sk="bbb",
        c_gsi1pk="ccc",
    )
    model_1.save()

    model_2 = TestModel(
        a_pk="yyy",
        b_sk="ccc",
        c_gsi1pk="ccc",
    )
    model_2.save()

    model_3 = TestModel(
        a_pk="zzz",
        b_sk="ccc",
        c_gsi1pk="other",
    )

    model_3.save()

    queryset = TestModel.objects.using(a_pk="aaa", c_gsi1pk="ccc").use_index(True)
    models = list(queryset)

    assert len(models) == 2
    # Models will be sorted by SK
    assert model_1 == models[0]
    assert model_2 == models[1]


def test_query_all_options(mock_table):
    """
    Tests all query options, some of which are not worth testing alone;
    Simply testing that they have been set should be enough.
    """

    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        c_gsi1pk = Field(str, gsi=True)

    queryset = (
        TestModel.objects.using(a_pk="aaa", b_sk="bbb", c_gsi1pk="ccc")
        .use_index(True)
        .limit(1)
        .starting_after(True)
        .reverse()
        .consistent(True)
        .only("a_pk", "b_sk")
    )

    assert queryset.get_query() == {
        "ConsistentRead": True,
        "ExpressionAttributeValues": {
            ":gsi1pk": {
                "S": "C#ccc#TestModel",
            },
            ":sk": {
                "S": "B#bbb",
            },
        },
        "IndexName": "GSI-1",
        "KeyConditionExpression": "GSI1PK = :gsi1pk AND SK > :sk",
        "ProjectionExpression": "a_pk, b_sk",
        "ScanIndexForward": False,
        "TableName": "unit-test-table",
    }
