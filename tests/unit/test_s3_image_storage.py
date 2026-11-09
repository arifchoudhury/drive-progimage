from app.images.infrastructure.storage import S3ImageStorage
from tests.fake_s3 import FakeS3Client


class TestS3ImageStorage:
    def test_object_key_includes_prefix_and_content_type_comes_from_the_key_suffix(self, fake_s3: FakeS3Client) -> None:
        S3ImageStorage("bucket", prefix="images/").save("abc.png", b"1")
        assert fake_s3.objects == {("bucket", "images/abc.png"): {"Body": b"1", "ContentType": "image/png"}}

    def test_unknown_suffix_falls_back_to_octet_stream(self, fake_s3: FakeS3Client) -> None:
        S3ImageStorage("bucket").save("abc.zzz", b"1")
        assert fake_s3.objects[("bucket", "abc.zzz")]["ContentType"] == "application/octet-stream"
