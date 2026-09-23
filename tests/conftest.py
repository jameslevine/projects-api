"""Shared fixtures: a moto-backed DynamoDB table shaped like the Terraform module."""

import os
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws

TABLE_NAME = "projects-test"

# Must be set before the app (and Powertools) is imported anywhere.
os.environ.setdefault("ENV", "local")
os.environ.setdefault("TABLE_NAME", TABLE_NAME)
os.environ.setdefault("AWS_REGION", "eu-west-2")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-2")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("POWERTOOLS_METRICS_NAMESPACE", "ProjectsApi")
os.environ.setdefault("POWERTOOLS_TRACE_DISABLED", "true")


@pytest.fixture
def dynamodb_table() -> Iterator[Any]:
    """Create the single table with the same keys and GSI as the Terraform module."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-west-2")
        client.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        yield client
