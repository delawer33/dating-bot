"""shared.storage.s3, shared.db.session, workers.db — small I/O surfaces."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

import shared.db.session as db_sess
import shared.storage.s3 as s3mod
from workers.db import create_async_engine_and_sessionmaker


def test_build_s3_client_calls_boto3() -> None:
    with patch.object(s3mod, "boto3") as b3:
        s3mod.build_s3_client("http://minio:9000", "k", "s", "us-east-1")
    b3.client.assert_called_once()


def test_ensure_bucket_exists_no_create() -> None:
    client = MagicMock()
    client.head_bucket.return_value = {}
    s3mod.ensure_bucket(client, "b")
    client.create_bucket.assert_not_called()


def test_ensure_bucket_creates_on_404() -> None:
    client = MagicMock()
    err = ClientError({"Error": {"Code": "404"}}, "HeadBucket")
    client.head_bucket.side_effect = err
    s3mod.ensure_bucket(client, "newbucket")
    client.create_bucket.assert_called_once_with(Bucket="newbucket")


def test_ensure_bucket_reraises_other_client_error() -> None:
    client = MagicMock()
    err = ClientError({"Error": {"Code": "AccessDenied"}}, "HeadBucket")
    client.head_bucket.side_effect = err
    with pytest.raises(ClientError):
        s3mod.ensure_bucket(client, "b")


def test_delete_and_presign_and_put_object() -> None:
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://signed"
    s3mod.delete_object(client, "bk", "key1")
    client.delete_object.assert_called_once()
    assert s3mod.presigned_get_url(client, "bk", "k2") == "https://signed"
    s3mod.put_object(client, "bk", "k3", b"x", "image/jpeg")
    s3mod.put_object(client, "bk", "k4", b"y", "image/png", {"a": "b"})
    assert client.put_object.call_count == 2


@pytest.mark.asyncio
async def test_get_session_raises_when_not_initialised() -> None:
    with patch.object(db_sess, "_session_factory", None):
        gen = db_sess.get_session()
        with pytest.raises(RuntimeError, match="DB not initialised"):
            await anext(gen)


def test_create_async_engine_passes_pool_settings() -> None:
    fake_engine = MagicMock()
    with patch("workers.db.SharedConfig") as cfg_cls:
        cfg = MagicMock()
        cfg.database_url = "postgresql+asyncpg://u:p@h/db"
        cfg.database_pool_size = 3
        cfg.database_max_overflow = 7
        cfg.database_pool_recycle = 999
        cfg_cls.return_value = cfg
        with patch("workers.db.create_async_engine", return_value=fake_engine) as ce:
            eng, _fac = create_async_engine_and_sessionmaker()
    assert eng is fake_engine
    ce.assert_called_once()
    kwargs = ce.call_args[1]
    assert kwargs["pool_size"] == 3
    assert kwargs["max_overflow"] == 7
    assert kwargs["pool_recycle"] == 999
