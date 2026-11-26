"""Recognise the photo formats fahrma stores (JPEG, WebP) and read their size, without an image library.

The app re-encodes every photo in the browser before sending it, so real uploads are plain
JPEGs. This check only makes sure that what is stored is what its type says: the file is served
with exactly that type, nosniff and a sandboxing Content-Security-Policy.
"""

import struct

MAX_SIDE = 10_000


class InvalidImage(ValueError):
    pass


def _jpeg_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\xff\xd8\xff"):
        raise InvalidImage("not a JPEG")
    position = 2
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            raise InvalidImage("broken JPEG segment")
        marker = data[position + 1]
        if marker == 0xFF:  # fill byte
            position += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            position += 2
            continue
        (length,) = struct.unpack(">H", data[position + 2 : position + 4])
        if length < 2:
            raise InvalidImage("broken JPEG segment")
        # Start of frame (not DHT C4, JPG C8, DAC CC): precision, height, width
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if position + 9 > len(data):
                break
            height, width = struct.unpack(">HH", data[position + 5 : position + 9])
            return width, height
        if marker == 0xDA:  # start of scan before any frame header
            break
        position += 2 + length
    raise InvalidImage("JPEG without a frame header")


def _webp_size(data: bytes) -> tuple[int, int]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise InvalidImage("not a WebP")
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8 ":
        if data[23:26] != b"\x9d\x01\x2a":
            raise InvalidImage("broken WebP")
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L":
        if data[20] != 0x2F:
            raise InvalidImage("broken WebP")
        bits = int.from_bytes(data[21:25], "little")
        return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
    raise InvalidImage("unknown WebP kind")


def image_size(data: bytes, content_type: str) -> tuple[int, int]:
    """(width, height) if ``data`` is an image of ``content_type``; raises InvalidImage otherwise."""
    if content_type == "image/jpeg":
        width, height = _jpeg_size(data)
    elif content_type == "image/webp":
        width, height = _webp_size(data)
    else:
        raise InvalidImage("unsupported type")
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
        raise InvalidImage("unusual image size")
    return width, height
