import os
import boto3
import botocore
import pytest
from moto import mock_aws

from single_table_orm import connection
from single_table_orm.connection import table  # Updated import
from single_table_orm.table_definition import get_standard_definition

TABLE_NAME = "unit-test-table"
# Must reflect actual table definition
TABLE_DEFINITION = get_standard_definition(TABLE_NAME)


@pytest.fixture(scope="function")
def mock_table():
    with mock_aws():
        dynamodb = boto3.client("dynamodb", region_name="us-east-1")
        dynamodb.create_table(**TABLE_DEFINITION)
        waiter = dynamodb.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)
        with connection.table.table_context(TABLE_NAME, client=dynamodb):
            yield dynamodb


@pytest.fixture()
def local_client():
    print("Setting up local DynamoDB client")
    host = os.getenv("DYNAMODB_HOST", "127.0.0.1")
    port = os.getenv("DYNAMODB_PORT", "8000")
    endpoint_url = f"http://{host}:{port}"

    # The key id and access key are fake, but they are required to
    # connect to the local DynamoDB instance.
    client = boto3.client(
        "dynamodb",
        region_name="us-east-1",
        aws_access_key_id="Fake",
        aws_secret_access_key="Fake",
        endpoint_url=endpoint_url,
    )

    try:
        client.create_table(
            **TABLE_DEFINITION,
        )
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print("Table already exists")
        else:
            raise

    # Set the connection to the test client
    with table.table_context(table_name=TABLE_NAME, client=client):
        yield client
    # Clean up any resources
    # Add waiter for table deletion
    try:
        client.delete_table(TableName=TABLE_NAME)
        waiter = client.get_waiter("table_not_exists")
        waiter.wait(TableName=TABLE_NAME)
        print(f"Table {TABLE_NAME} deleted successfully.")
    except botocore.exceptions.ClientError as e:
        print(f"Error deleting table {TABLE_NAME}: {e}")
