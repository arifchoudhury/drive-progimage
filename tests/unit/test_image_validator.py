from collections.abc import Callable

import pytest

from app.images.domain.exceptions import ImageTooLargeError, InvalidImageError, UnsupportedImageFormatError
from app.images.domain.validation import ImageValidator
from tests.samples import png_header

MiB = 1024 * 1024


@pytest.fixture
def validator() -> ImageValidator:
    return ImageValidator(max_bytes=MiB, max_pixels=1_000_000)


class TestAccepts:
    @pytest.mark.parametrize(
        ("fmt", "content_type", "extension"),
        [
            ("PNG", "image/png", "png"),
            ("JPEG", "image/jpeg", "jpg"),
            ("GIF", "image/gif", "gif"),
            ("WEBP", "image/webp", "webp"),
        ],
    )
    def test_web_formats_with_detected_metadata(
        self,
        validator: ImageValidator,
        make_image: Callable[[str], bytes],
        fmt: str,
        content_type: str,
        extension: str,
    ) -> None:
        data = make_image(fmt)

        info = validator.validate(data)

        assert (info.content_type, info.extension, info.size_bytes) == (content_type, extension, len(data))

    def test_exactly_max_bytes(self, make_image: Callable[[str], bytes]) -> None:
        data = make_image("PNG")
        ImageValidator(max_bytes=len(data), max_pixels=1_000_000).validate(data)

    def test_exactly_max_pixels(self, make_image: Callable[[str], bytes]) -> None:
        ImageValidator(max_bytes=MiB, max_pixels=20 * 10).validate(make_image("PNG"))  # fixture images are 20x10


class TestRejects:
    @pytest.mark.parametrize("data", [b"", b"definitely not an image", b"\x89PNG\r\n\x1a\n"])
    def test_non_images_as_invalid(self, validator: ImageValidator, data: bytes) -> None:
        with pytest.raises(InvalidImageError):
            validator.validate(data)

    def test_truncated_image_as_invalid(self, validator: ImageValidator, truncated_png: bytes) -> None:
        with pytest.raises(InvalidImageError):
            validator.validate(truncated_png)

    @pytest.mark.parametrize("fmt", ["TIFF", "BMP", "ICO"])
    def test_real_images_in_other_formats_as_unsupported(
        self, validator: ImageValidator, make_image: Callable[[str], bytes], fmt: str
    ) -> None:
        with pytest.raises(UnsupportedImageFormatError) as exc_info:
            validator.validate(make_image(fmt))
        assert exc_info.value.image_format == fmt

    def test_one_byte_over_max_bytes_as_too_large(self, make_image: Callable[[str], bytes]) -> None:
        data = make_image("PNG")
        with pytest.raises(ImageTooLargeError) as exc_info:
            ImageValidator(max_bytes=len(data) - 1, max_pixels=1_000_000).validate(data)
        assert exc_info.value.max_bytes == len(data) - 1

    def test_one_pixel_over_max_pixels_as_invalid(self, make_image: Callable[[str], bytes]) -> None:
        with pytest.raises(InvalidImageError):
            ImageValidator(max_bytes=MiB, max_pixels=20 * 10 - 1).validate(make_image("PNG"))

    @pytest.mark.parametrize(
        ("width", "height"),
        [
            (5_000, 5_000),  # over our max_pixels, under Pillow's own limits
            (12_000, 12_000),  # past Pillow's DecompressionBombWarning threshold
            (100_000, 100_000),  # past its DecompressionBombError threshold: used to escape as a 500
        ],
    )
    def test_decompression_bomb_headers_as_invalid_without_decoding(
        self, validator: ImageValidator, width: int, height: int
    ) -> None:
        with pytest.raises(InvalidImageError):
            validator.validate(png_header(width, height))
