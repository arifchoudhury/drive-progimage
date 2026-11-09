"""ImageStorage adapters.

Adding a backend = a new module here + a `case` in get_storage (app/images/api/dependencies.py).
"""

from app.images.infrastructure.storage.local import LocalImageStorage
from app.images.infrastructure.storage.s3 import S3ImageStorage

__all__ = ["LocalImageStorage", "S3ImageStorage"]
