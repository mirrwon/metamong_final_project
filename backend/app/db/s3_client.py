import os
from typing import Dict, Optional, Tuple
from urllib.parse import quote

from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

_last_error: Optional[str] = None
_client_cache: Dict[Tuple[str, str, str], object] = {}


def _get_settings() -> Tuple[str, str, str, str, str, int]:
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    region = os.getenv("AWS_REGION", "").strip()
    bucket = os.getenv("S3_BUCKET", "").strip()
    access_point_arn = os.getenv("S3_ACCESS_POINT_ARN", "").strip()
    expires_raw = os.getenv("S3_PRESIGN_EXPIRES_SEC", "").strip()
    try:
        expires = max(60, min(int(expires_raw), 604800))
    except Exception:
        expires = 900
    return access_key, secret_key, region, bucket, access_point_arn, expires


def _bucket_id(bucket: str, access_point_arn: str) -> str:
    return access_point_arn or bucket


def _get_client(access_key: str, secret_key: str, region: str):
    cache_key = (access_key, secret_key, region)
    client = _client_cache.get(cache_key)
    if client is not None:
        return client

    try:
        import boto3
        from botocore.config import Config
    except Exception as exc:
        raise RuntimeError(f"missing_boto3:{exc!r}")

    config = Config(signature_version="s3v4", s3={"use_arn_region": True})
    client = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=config,
    )
    _client_cache[cache_key] = client
    return client


def ping_s3() -> bool:
    global _last_error
    access_key, secret_key, region, bucket, access_point_arn, _ = _get_settings()
    if not bucket and not access_point_arn:
        _last_error = "missing_bucket"
        return False
    if not access_key or not secret_key:
        _last_error = "missing_credentials"
        return False
    if not region:
        _last_error = "missing_region"
        return False

    try:
        client = _get_client(access_key, secret_key, region)
        bucket_id = _bucket_id(bucket, access_point_arn)
        client.list_objects_v2(Bucket=bucket_id, MaxKeys=1)
    except Exception as exc:
        _last_error = repr(exc)
        return False

    _last_error = None
    return True


def get_s3_error() -> Optional[str]:
    return _last_error


def get_presigned_url(key: str) -> Optional[str]:
    global _last_error
    access_key, secret_key, region, bucket, access_point_arn, expires = _get_settings()
    if not key:
        _last_error = "missing_key"
        return None
    if not access_key or not secret_key:
        _last_error = "missing_credentials"
        return None
    if not region:
        _last_error = "missing_region"
        return None
    if not bucket and not access_point_arn:
        _last_error = "missing_bucket"
        return None

    try:
        client = _get_client(access_key, secret_key, region)
        bucket_id = _bucket_id(bucket, access_point_arn)
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_id, "Key": key},
            ExpiresIn=expires,
        )
    except Exception as exc:
        _last_error = repr(exc)
        return None

    _last_error = None
    return url


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
    global _last_error
    access_key, secret_key, region, bucket, access_point_arn, _ = _get_settings()
    if not key:
        _last_error = "missing_key"
        return False
    if not data:
        _last_error = "missing_data"
        return False
    if not access_key or not secret_key:
        _last_error = "missing_credentials"
        return False
    if not region:
        _last_error = "missing_region"
        return False
    if not bucket and not access_point_arn:
        _last_error = "missing_bucket"
        return False

    try:
        client = _get_client(access_key, secret_key, region)
        bucket_id = _bucket_id(bucket, access_point_arn)
        params = {
            "Bucket": bucket_id,
            "Key": key,
            "Body": data,
            "ContentType": content_type or "application/octet-stream",
        }
        acl = os.getenv("S3_UPLOAD_ACL", "").strip()
        if acl:
            params["ACL"] = acl
        client.put_object(**params)
    except Exception as exc:
        _last_error = repr(exc)
        return False

    _last_error = None
    return True


def get_object_url(key: str, prefer_presigned: bool = False) -> Optional[str]:
    if not key:
        return None

    public_base = os.getenv("S3_PUBLIC_BASE_URL", "").strip()
    if public_base:
        return f"{public_base.rstrip('/')}/{quote(key)}"

    force_presigned = os.getenv("S3_FORCE_PRESIGNED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    access_key, secret_key, region, bucket, access_point_arn, _ = _get_settings()

    if (prefer_presigned or force_presigned) and access_key and secret_key and region and (bucket or access_point_arn):
        return get_presigned_url(key)

    if bucket and region:
        return f"https://{bucket}.s3.{region}.amazonaws.com/{quote(key)}"

    if access_key and secret_key and region and (bucket or access_point_arn):
        return get_presigned_url(key)

    return None
