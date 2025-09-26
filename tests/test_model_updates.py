from single_table_orm.fields import Field
from single_table_orm.models import Model
from tests.utils import mock_table  # noqa: F401


def test_model_remove_field(mock_table):  # noqa: F811
    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)
        to_remove_attribute = Field(str)

    model = TestModel(
        a_pk="aaa",
        b_sk="bbb",
        another_attribute="another",
        to_remove_attribute="to_remove",
    )
    model.save()

    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)

    model = TestModel.objects.get(
        a_pk="aaa",
        b_sk="bbb",
    )
    assert model.another_attribute == "another"


def test_model_add_field(mock_table):  # noqa: F811
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

    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)
        new_attribute = Field(str)

    model = TestModel.objects.get(
        a_pk="aaa",
        b_sk="bbb",
    )
    assert model.new_attribute is None
    assert model.another_attribute == "another"

    model.update(new_attribute="new")
    model = TestModel.objects.get(
        a_pk="aaa",
        b_sk="bbb",
    )
    assert model.new_attribute == "new"
    assert model.another_attribute == "another"


def test_model_update_field_on_updated_model(mock_table):  # noqa: F811
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

    class TestModel(Model):
        a_pk = Field(str, pk=True)
        b_sk = Field(str, sk=True)
        another_attribute = Field(str)
        new_field = Field(str)

    model = TestModel.objects.get(
        a_pk="aaa",
        b_sk="bbb",
    )
    model.update(another_attribute="updated")

    model = TestModel.objects.get(
        a_pk="aaa",
        b_sk="bbb",
    )
    assert model.another_attribute == "updated"
    assert model.new_field is None
