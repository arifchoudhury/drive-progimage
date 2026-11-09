class ImageRejectedError(Exception):
    """Base for every reason an upload is refused. The API maps each subclass to its own status code."""


class InvalidImageError(ImageRejectedError):
    """Not a decodable image: empty, corrupt or truncated, or too many pixels."""


class UnsupportedImageFormatError(ImageRejectedError):
    """A real image, but in a format the service doesn't accept."""

    def __init__(self, image_format: str) -> None:
        super().__init__(image_format)
        self.image_format = image_format


class ImageTooLargeError(ImageRejectedError):
    def __init__(self, max_bytes: int) -> None:
        super().__init__(max_bytes)
        self.max_bytes = max_bytes


class ImageNotFoundError(Exception):
    pass
