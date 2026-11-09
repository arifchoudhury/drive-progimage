import struct
import zlib


def png_header(width: int, height: int) -> bytes:
    """Just a PNG signature + IHDR chunk claiming the given size: what a decompression-bomb probe looks like.

    Pillow reads the size from the header alone, so no pixel data is needed to trigger its size checks.
    """
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB, no interlace
    chunk = b"IHDR" + ihdr
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(ihdr)) + chunk + struct.pack(">I", zlib.crc32(chunk))
