import mimetypes


class S3ImageStorage:
    """ImageStorage that stores each image as the object `<prefix><key>`; the key's extension sets its ContentType.

    boto3 is imported lazily (optional `s3` extra), so local runs don't need it. Tests patch `boto3.client`.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        *,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        import boto3

        self._client = boto3.client(
            "s3",
            region_name=region_name,
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        self._bucket = bucket
        self._prefix = prefix

    def save(self, key: str, data: bytes) -> None:
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        self._client.put_object(Bucket=self._bucket, Key=self._key(key), Body=data, ContentType=content_type)

    def load(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=self._key(key))
        except self._client.exceptions.NoSuchKey:
            return None
        body: bytes = response["Body"].read()
        return body

    def check(self) -> None:
        # Raises if the bucket is missing or the credentials can't reach it.
        self._client.head_bucket(Bucket=self._bucket)

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"
