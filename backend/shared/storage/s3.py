"""S3-compatible storage (MinIO / AWS) — sync boto3; use asyncio.to_thread from async routes."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, BinaryIO

import boto3
from botocore.client import BaseClient
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def build_s3_client(
    endpoint_url: str,
    access_key: str,
    secret_key: str,
    region: str,
) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=BotoConfig(
            s3={"addressing_style": "path"},
            signature_version="s3v4",
        ),
    )


def ensure_bucket(client: BaseClient, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:  # pragma: no cover
        err = (exc.response.get("Error") or {}).get("Code", "")
        if err in ("404", "NoSuchBucket", "NotFound"):
            client.create_bucket(Bucket=bucket)
            logger.info("Created S3 bucket %r", bucket)
        else:
            raise


def delete_object(client: BaseClient, bucket: str, key: str) -> None:
    client.delete_object(Bucket=bucket, Key=key)


def presigned_get_url(client: BaseClient, bucket: str, key: str, expires_in: int = 3600) -> str:
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def put_object(
    client: BaseClient,
    bucket: str,
    key: str,
    body: bytes | BinaryIO,
    content_type: str,
    extra_metadata: Mapping[str, str] | None = None,
) -> None:
    kwargs: dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "Body": body,
        "ContentType": content_type,
    }
    if extra_metadata:
        kwargs["Metadata"] = dict(extra_metadata)
    client.put_object(**kwargs)
