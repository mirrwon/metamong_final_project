import boto3

s3 = boto3.client("s3")

def s3_download(bucket: str, key: str, dst_path: str):
    s3.download_file(bucket, key, dst_path)

def s3_upload(bucket: str, key: str, src_path: str, content_type=None):
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    s3.upload_file(src_path, bucket, key, ExtraArgs=extra if extra else None)
