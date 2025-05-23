import pytest
from single_table_orm.fields import Field
from single_table_orm.models import F, Model, ObjectAlreadyExists, ObjectDoesNotExist
from utils import local_client  # Updated import
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

        class Meta:
            suffix = "TestModel"

    model = TestModel(
        a_pk="aaa",
        b_pk="bbb",
        c_sk="ccc",
        d_sk="ddd",
        e_gsi="eee",
        f_gsi="fff",
        another_attribute="another",
    )

    assert model.get_pk() == "TestModel#A#aaa#B#bbb#TestModel"  # Suffix start and end
    assert model.get_sk() == "C#ccc#D#ddd"  # No suffix
    assert (
        model.get_gsi1pk() == "TestModel#E#eee#F#fff#TestModel"
    )  # Suffix start and end


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

    assert model.get_pk() == "ChangedSuffix#V#value_1#ChangedSuffix"
    assert model.get_sk() == "V#value_2"
    assert model.get_gsi1pk() == "ChangedSuffix#V#value_3#ChangedSuffix"


def test_is_key_valid():
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_pk = Field(str, sk=True)
        c_sk = Field(str, gsi=True)
        another_attribute = Field(str)

        class Meta:
            suffix = "TestModel"

    model = TestModel(
        a_pk=None,
        b_sk=None,
        c_gsi1pk=None,
        another_attribute="another",
    )

    with pytest.raises(Exception):
        model.get_pk()

    with pytest.raises(Exception):
        model.get_sk()

    # GSI is allowed to be None
    assert model.get_gsi1pk() is None


def test_model_get_exists(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

        class Meta:
            suffix = "TestModel"

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
    )

    local_client.put_item(
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


def test_model_get_does_not_exist(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

        class Meta:
            suffix = "TestModel"

    # Do not create anything

    with pytest.raises(ObjectDoesNotExist):
        TestModel.objects.get(a_pk="aaa", b_sk="bbb")


def test_save(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

        class Meta:
            suffix = "TestModel"

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
    )
    model.save()

    result = local_client.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model.get_pk()},  # TestModel#A#aaa#TestModel
            "SK": {"S": model.get_sk()},  # B#bbb
        },
    )
    assert "Item" in result
    expected_item = {
        "PK": {
            "S": "TestModel#A#aaa#TestModel",
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
    # Add GSI1PK if it exists
    gsi1pk = model.get_gsi1pk()
    if gsi1pk:
        expected_item["GSI1PK"] = {"S": gsi1pk}

    assert result["Item"] == expected_item


def test_save_allow_override(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

        class Meta:
            suffix = "TestModel"

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

    result = local_client.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model_2.get_pk()},
            "SK": {"S": model_2.get_sk()},
        },
    )
    assert model_1.get_pk() == model_2.get_pk()
    assert model_1.get_sk() == model_2.get_sk()

    assert "Item" in result
    expected_item = {
        "PK": {
            "S": "TestModel#A#aaa#TestModel",
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
    # Add GSI1PK if it exists
    gsi1pk = model_2.get_gsi1pk()
    if gsi1pk:
        expected_item["GSI1PK"] = {"S": gsi1pk}

    assert result["Item"] == expected_item


def test_save_prevent_override(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

        class Meta:
            suffix = "TestModel"

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


def test_delete(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

        class Meta:
            suffix = "TestModel"

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
    )
    local_client.put_item(
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

    result = local_client.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model.get_pk()},
            "SK": {"S": model.get_sk()},
        },
    )
    assert "Item" not in result


def test_update(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)
        updating_attribute = Field(str)

        class Meta:
            suffix = "TestModel"

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
        updating_attribute="old",
    )
    item_to_put = {
        "PK": {"S": model.get_pk()},
        "SK": {"S": model.get_sk()},
        "a_pk": {"S": model.a_pk},
        "b_sk": {"S": model.b_sk},
        "another_attribute": {"S": model.another_attribute},
        "updating_attribute": {"S": model.updating_attribute},
    }
    # Add GSI1PK if it exists
    gsi1pk = model.get_gsi1pk()
    if gsi1pk:
        item_to_put["GSI1PK"] = {"S": gsi1pk}

    local_client.put_item(
        TableName=table.table_name,
        Item=item_to_put,
    )

    model.update(updating_attribute="new")

    # Assert that the instance was updated
    assert model.updating_attribute == "new"

    result = local_client.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model.get_pk()},
            "SK": {"S": model.get_sk()},
        },
    )
    assert "Item" in result
    expected_item = {
        "PK": {
            "S": "TestModel#A#aaa#TestModel",
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
            "S": "new",
        },
    }
    # Add GSI1PK if it exists
    gsi1pk_updated = model.get_gsi1pk()
    if gsi1pk_updated:
        expected_item["GSI1PK"] = {"S": gsi1pk_updated}

    assert result["Item"] == expected_item


def test_update_using_expression(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)
        updating_attribute = Field(int)

        class Meta:
            suffix = "TestModel"

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
        updating_attribute=1,
    )
    item_to_put = {
        "PK": {"S": model.get_pk()},
        "SK": {"S": model.get_sk()},
        "a_pk": {"S": model.a_pk},
        "b_sk": {"S": model.b_sk},
        "another_attribute": {"S": model.another_attribute},
        "updating_attribute": {"N": str(model.updating_attribute)},
    }
    # Add GSI1PK if it exists
    gsi1pk = model.get_gsi1pk()
    if gsi1pk:
        item_to_put["GSI1PK"] = {"S": gsi1pk}

    local_client.put_item(
        TableName=table.table_name,
        Item=item_to_put,
    )

    model.update(updating_attribute=F("updating_attribute") + 1)

    # Assert that the instance was updated
    assert model.updating_attribute == 2

    result = local_client.get_item(
        TableName=table.table_name,
        Key={
            "PK": {"S": model.get_pk()},
            "SK": {"S": model.get_sk()},
        },
    )
    assert "Item" in result
    expected_item = {
        "PK": {"S": "TestModel#A#aaa#TestModel"},
        "SK": {"S": "B#bbb"},
        "a_pk": {"S": "aaa"},
        "b_sk": {"S": "bbb"},
        "another_attribute": {"S": "another"},
        "updating_attribute": {"N": "2"},
    }
    # Add GSI1PK if it exists
    gsi1pk_updated = model.get_gsi1pk()
    if gsi1pk_updated:
        expected_item["GSI1PK"] = {"S": gsi1pk_updated}

    assert result["Item"] == expected_item


def test_query(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)

        class Meta:
            suffix = "TestModel"

    models = [TestModel(a_pk="aaa", b_sk=f"bbb_{i}") for i in range(3)]
    for model in models:
        model.save()

    results = list(TestModel.objects.using(a_pk="aaa"))
    assert len(results) == 3
    # Check if results match the original models (order might differ)
    assert set(results) == set(models)


def test_query_limit(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)

        class Meta:
            suffix = "TestModel"

    models = [TestModel(a_pk="aaa", b_sk=f"bbb_{i}") for i in range(3)]
    for model in models:
        model.save()

    queryset = TestModel.objects.using(a_pk="aaa").limit(2)
    results = list(queryset)

    assert len(results) == 2
    # Check pagination key
    assert queryset.last_evaluated_key is not None


def test_query_limit_starting_after(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)

        class Meta:
            suffix = "TestModel"

    models = [TestModel(a_pk="aaa", b_sk=f"bbb_{i}") for i in range(3)]
    for model in models:
        model.save()

    queryset1 = TestModel.objects.using(a_pk="aaa").limit(2)
    results1 = list(queryset1)
    assert len(results1) == 2
    last_key = queryset1.last_evaluated_key

    queryset2 = TestModel.objects.using(a_pk="aaa").limit(2).starting_after(last_key)
    results2 = list(queryset2)
    assert len(results2) == 1
    assert queryset2.last_evaluated_key is None


def test_query_use_index(local_client):
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        c_gsi1pk = Field(str, gsi=True)

        class Meta:
            suffix = "TestModel"

    # Create models with different PKs but same GSI1PK
    model1 = TestModel(a_pk="aaa1", b_sk="bbb1", c_gsi1pk="ccc")
    model2 = TestModel(a_pk="aaa2", b_sk="bbb2", c_gsi1pk="ccc")
    # Create a model with a different GSI1PK
    model3 = TestModel(a_pk="aaa3", b_sk="bbb3", c_gsi1pk="ddd")

    model1.save()
    model2.save()
    model3.save()

    # Query using GSI1
    # Note: The query uses the GSI1PK format (Suffix#Identifier#Value#Suffix)
    results = list(TestModel.objects.using(c_gsi1pk="ccc").use_index(True))

    assert len(results) == 2
    assert set(results) == {model1, model2}

    # Test querying GSI1 without GSI fields raises error (now returns None, so query fails)
    with pytest.raises(ValueError):
        list(TestModel.objects.using(a_pk="some_pk").use_index(True))


def test_query_all_options(local_client):
    """
    Test querying with multiple options enabled:
    - use_index(True)
    - limit(1)
    - reverse()
    - only("a_pk")
    - consistent(True)
    """

    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        c_gsi1pk = Field(str, gsi=True)
        d_other = Field(str)

        class Meta:
            suffix = "TestModel"

    # Create models with different PKs but same GSI1PK
    model1 = TestModel(a_pk="aaa1", b_sk="bbb1", c_gsi1pk="ccc", d_other="d1")
    model2 = TestModel(a_pk="aaa2", b_sk="bbb2", c_gsi1pk="ccc", d_other="d2")

    model1.save()
    model2.save()

    queryset = (
        TestModel.objects.using(c_gsi1pk="ccc")
        .use_index(True)
        .limit(1)
        .reverse()
        .only("a_pk")
        .consistent(True)
    )

    results = list(queryset)

    assert len(results) == 1
    # Check only the specified field is present (PK/SK/GSI are always included implicitly by DB)
    # Here we only check the projected attribute `a_pk`. The other attribute `d_other` should not be present.
    retrieved_model = results[0]
    assert hasattr(retrieved_model, "a_pk")
    assert not hasattr(retrieved_model, "d_other")
    assert retrieved_model.a_pk in ["aaa1", "aaa2"]

    # Check pagination occurred
    assert queryset.last_evaluated_key is not None
