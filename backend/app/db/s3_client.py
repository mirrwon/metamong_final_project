import os
from typing import Optional, Tuple, Dict

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

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


def _resolve_bucket_id(bucket: str, access_point_arn: str) -> str:
    return access_point_arn or bucket


def _validate_base_settings(
    access_key: str, secret_key: str, region: str, bucket: str, access_point_arn: str
) -> Optional[str]:
    if not bucket and not access_point_arn:
        return "missing_bucket"
    if not access_key or not secret_key:
        return "missing_credentials"
    if not region:
        return "missing_region"
    return None


def _sign_get_object_url(client, bucket_id: str, key: str, expires: int) -> str:
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_id, "Key": key},
        ExpiresIn=expires,
    )


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
    validation_error = _validate_base_settings(access_key, secret_key, region, bucket, access_point_arn)
    if validation_error:
        _last_error = validation_error
        return False

    try:
        client = _get_client(access_key, secret_key, region)
        bucket_id = _resolve_bucket_id(bucket, access_point_arn)
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
    validation_error = _validate_base_settings(access_key, secret_key, region, bucket, access_point_arn)
    if validation_error:
        _last_error = validation_error
        return None

    try:
        client = _get_client(access_key, secret_key, region)
        bucket_id = _resolve_bucket_id(bucket, access_point_arn)
        url = _sign_get_object_url(client, bucket_id, key, expires)
    except Exception as exc:
        _last_error = repr(exc)
        return None

    _last_error = None
    return url


def get_existing_presigned_url(keys: list[str]) -> Optional[str]:
    global _last_error
    access_key, secret_key, region, bucket, access_point_arn, expires = _get_settings()
    if not keys:
        _last_error = "missing_keys"
        return None
    validation_error = _validate_base_settings(access_key, secret_key, region, bucket, access_point_arn)
    if validation_error:
        _last_error = validation_error
        return None

    try:
        client = _get_client(access_key, secret_key, region)
        bucket_id = _resolve_bucket_id(bucket, access_point_arn)
        valid_keys = [k for k in keys if k]
        if not valid_keys:
            _last_error = "missing_keys"
            return None

        for key in valid_keys:
            search_prefix = key.rsplit(".", 1)[0]
            try:
                listed = client.list_objects_v2(Bucket=bucket_id, Prefix=search_prefix, MaxKeys=20)
                existing = {obj.get("Key") for obj in listed.get("Contents", []) if obj.get("Key")}
            except Exception:
                existing = set()
            if key in existing:
                url = _sign_get_object_url(client, bucket_id, key, expires)
                _last_error = None
                return url

        # Fallback: in some buckets list permission can be limited.
        for key in valid_keys:
            try:
                client.head_object(Bucket=bucket_id, Key=key)
            except Exception:
                continue
            url = _sign_get_object_url(client, bucket_id, key, expires)
            _last_error = None
            return url
    except Exception as exc:
        _last_error = repr(exc)
        return None

    _last_error = "not_found"
    return None
