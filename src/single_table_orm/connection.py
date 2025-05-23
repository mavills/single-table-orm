import os
from contextlib import contextmanager

import boto3


class ConnectionManager:
    """
    Keep track of the current table being used by the connection
    """

    def __init__(self, table_name: str = None):
        """
        Initialize the connection manager with the default table name
        """
        self._default_table = table_name
        self._current_table = self._default_table
        self._client = None

    def _create_client(self):
        """
        Create an actual boto3 client connection
        """
        # In reality, this would use boto3
        # return boto3.client("dynamodb", endpoint_url="http://localhost:8000")
        return boto3.client("dynamodb")

    @property
    def client(self):
        """
        Keep track of the current client connection
        """
        if self._client is None:
            # Create a new client connection when it has not been created yet
            self._client = self._create_client()
        return self._client

    @client.setter
    def client(self, client):
        self._client = client

    @property
    def table_name(self):
        """
        The current table name.
        """
        if self.client is None:
            # Create a new client connection when it has not been created yet
            self.client = self._create_client()
        return self._current_table

    @table_name.setter
    def table_name(self, table_name):
        print(f"Switching to table: {table_name}")
        self._current_table = table_name
        if self._connection:
            self._connection["table"] = table_name

    @contextmanager
    def table_context(self, table_name: str = None, client=None):
        original_table = self._current_table
        # Use private attribute to avoid creating a new client
        original_client = self._client
        # Switch to the new table
        if table_name is not None:
            self._current_table = table_name
        if client is not None:
            self.client = client
        try:
            yield self
        finally:
            self._current_table = original_table
            self.client = original_client


# Singleton instance
table = ConnectionManager(table_name=os.getenv("DB_TABLE_NAME"))
