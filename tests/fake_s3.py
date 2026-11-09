import io
from typing import Any


class FakeS3Client:
    """In-memory stand-in for the boto3 S3 client methods S3ImageStorage uses."""

    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = {"Body": Body, "ContentType": ContentType}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        try:
            return {"Body": io.BytesIO(self.objects[(Bucket, Key)]["Body"])}
        except KeyError:
            raise self.exceptions.NoSuchKey(Key) from None
