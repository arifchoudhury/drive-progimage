import io

from PIL import Image, UnidentifiedImageError

from app.images.domain.exceptions import (
    ImageRejectedError,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageFormatError,
)
from app.images.domain.values import ImageInfo

# Web-safe formats only. Pillow can open many more (EPS, TIFF, PSD, ICO, ...), which we don't want to store and
# serve back under our origin.
DEFAULT_ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "GIF", "WEBP"})

# Pillow format name -> file extension, where plain lower-casing isn't the conventional one.
_EXTENSION_OVERRIDES = {"JPEG": "jpg"}


class ImageValidator:
    """The upload policy: what counts as an acceptable image. Pure rules, no I/O.

    Checks run cheapest first, and everything before `verify()` reads only the header, so a hostile file is
    rejected before any pixel data is decoded.

    `max_bytes` is defence in depth: over HTTP, MaxBodySizeMiddleware rejects oversized bodies before they are
    parsed. The check here keeps the rule true for any other caller.

    Known limit: `verify()` checks PNG/GIF structure and checksums but does little for JPEG, so a truncated JPEG
    can pass. Catching that needs a full `load()` (a decode of every upload, up to ~4 bytes x max_pixels of
    memory), which we have chosen not to pay for.
    """

    def __init__(
        self, *, max_bytes: int, max_pixels: int, allowed_formats: frozenset[str] = DEFAULT_ALLOWED_FORMATS
    ) -> None:
        self._max_bytes = max_bytes
        self._max_pixels = max_pixels
        self._allowed_formats = allowed_formats

    def validate(self, data: bytes) -> ImageInfo:
        if not data:
            raise InvalidImageError()
        if len(data) > self._max_bytes:
            raise ImageTooLargeError(self._max_bytes)

        try:
            # Pillow raises DecompressionBombError from open() when the header claims an absurd size.
            with Image.open(io.BytesIO(data)) as img:
                fmt = img.format or ""
                width, height = img.size
                if fmt not in self._allowed_formats:
                    raise UnsupportedImageFormatError(fmt)
                # Our own limit, from the header alone. Pillow's MAX_IMAGE_PIXELS is process-global; we leave it.
                if width * height > self._max_pixels:
                    raise InvalidImageError()
                img.verify()
        except ImageRejectedError:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise InvalidImageError() from exc
        except Exception as exc:  # verify() raises a variety of types (SyntaxError, OSError, struct.error, ...)
            raise InvalidImageError() from exc

        return ImageInfo(
            content_type=Image.MIME[fmt],
            extension=_EXTENSION_OVERRIDES.get(fmt, fmt.lower()),
            size_bytes=len(data),
        )
