from pathlib import Path


class LocalImageStorage:
    """Stores each image as the file `<root>/<key>`, so the files open normally when browsing the folder."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes) -> None:
        self._path(key).write_bytes(data)

    def load(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"storage key escapes the storage root: {key!r}")
        return path
