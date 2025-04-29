import os
import boto3
import botocore
import pytest

from single_table_orm.connection import table # Updated import

TABLE_NAME = "unit-test-table"
# Must reflect actual table definition
TABLE_DEFINITION = {
    "TableName": TABLE_NAME,
    "KeySchema": [
        {"AttributeName": "PK", "KeyType": "HASH"},
        {"AttributeName": "SK", "KeyType": "RANGE"},
    ],
    "AttributeDefinitions": [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
        {"AttributeName": "GSI1PK", "AttributeType": "S"},
    ],
    "GlobalSecondaryIndexes": [
        {
            # Corrected IndexName to match query logic
            "IndexName": "GSI1",
            "KeySchema": [
                {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                # Corrected GSI KeySchema: SK should be part of GSI1
                # No, SK can be RANGE key for GSI. Let's assume it's correct.
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 1,
                "WriteCapacityUnits": 1,
            },
        }
    ],
    "ProvisionedThroughput": {"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
}


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