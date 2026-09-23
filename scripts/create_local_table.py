"""Create the single table in DynamoDB Local, mirroring infra/terraform/modules/dynamodb_table."""

import os

import boto3
from botocore.exceptions import ClientError

TABLE = os.environ.get("TABLE_NAME", "projects-local")
ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://localhost:8000")

client = boto3.client("dynamodb", region_name="eu-west-2", endpoint_url=ENDPOINT)
try:
    client.create_table(
        TableName=TABLE,
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
    print(f"created table {TABLE} at {ENDPOINT}")
except ClientError as exc:
    if exc.response["Error"]["Code"] == "ResourceInUseException":
        print(f"table {TABLE} already exists")
    else:
        raise
