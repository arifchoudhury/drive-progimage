from pathlib import Path

import pytest

from app.images.infrastructure.storage import LocalImageStorage


class TestLocalImageStorage:
    def test_save_then_load_round_trips_bytes(self, tmp_path: Path) -> None:
        storage = LocalImageStorage(tmp_path)
        storage.save("abc.png", b"\x00\x01data")
        assert storage.load("abc.png") == b"\x00\x01data"

    def test_file_is_named_exactly_the_key(self, tmp_path: Path) -> None:
        LocalImageStorage(tmp_path).save("abc.png", b"1")
        assert [p.name for p in tmp_path.iterdir()] == ["abc.png"]

    def test_load_of_unknown_key_is_none(self, tmp_path: Path) -> None:
        assert LocalImageStorage(tmp_path).load("missing.png") is None

    def test_creates_the_root_directory_when_absent(self, tmp_path: Path) -> None:
        root = tmp_path / "nested" / "images"
        LocalImageStorage(root)
        assert root.is_dir()

    def test_images_are_isolated_by_key(self, tmp_path: Path) -> None:
        storage = LocalImageStorage(tmp_path)
        storage.save("a.png", b"1")
        storage.save("b.jpg", b"2")
        assert (storage.load("a.png"), storage.load("b.jpg")) == (b"1", b"2")

    @pytest.mark.parametrize("key", ["../escape.png", "/etc/passwd", "sub/../../escape.png"])
    def test_keys_that_escape_the_root_are_rejected(self, tmp_path: Path, key: str) -> None:
        root = tmp_path / "root"
        storage = LocalImageStorage(root)
        with pytest.raises(ValueError, match="escapes"):
            storage.save(key, b"x")
        with pytest.raises(ValueError, match="escapes"):
            storage.load(key)
