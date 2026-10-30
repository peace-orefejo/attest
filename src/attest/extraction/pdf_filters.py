from __future__ import annotations

import base64
import zlib

from pypdf.generic import StreamObject

from .pdf_objects import as_object_list, resolve


def decode_stream_bounded(stream: StreamObject, remaining: int, limit: int) -> bytes:
    data = _raw_stream_bytes(stream)
    for name in _filter_names(stream):
        data = _apply_filter(name, data, remaining, limit)
        _require_within(data, remaining, limit)
    _require_within(data, remaining, limit)
    return data


def _raw_stream_bytes(stream: StreamObject) -> bytes:
    data: object = vars(stream).get("_data")
    if not isinstance(data, bytes):
        raise ValueError("Malformed PDF: stream has no raw data")
    return data


def _filter_names(stream: StreamObject) -> list[str]:
    filters: object = stream.get("/Filter")
    if filters is None:
        return []
    resolved = resolve(filters)
    items = as_object_list(resolved)
    if items is None:
        return [str(resolved)]
    return [str(item) for item in items]


def _apply_filter(name: str, data: bytes, remaining: int, limit: int) -> bytes:
    if name in {"/ASCII85Decode", "/A85"}:
        return base64.a85decode(data, adobe=True)
    if name in {"/ASCIIHexDecode", "/AHx"}:
        return _ascii_hex_decode(data)
    if name in {"/FlateDecode", "/Fl"}:
        return _bounded_flate_decode(data, remaining, limit)
    if name in {"/RunLengthDecode", "/RL"}:
        return _bounded_run_length_decode(data, remaining, limit)
    raise ValueError(f"PDF content filter cannot be bounded safely: {name}")


def _ascii_hex_decode(data: bytes) -> bytes:
    compact = b"".join(data.split()).removesuffix(b">")
    if len(compact) % 2:
        compact += b"0"
    return bytes.fromhex(compact.decode("ascii"))


def _bounded_flate_decode(data: bytes, remaining: int, limit: int) -> bytes:
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(data, remaining + 1)
    if len(decoded) > remaining or not decoder.eof:
        raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
    return decoded


def _bounded_run_length_decode(data: bytes, remaining: int, limit: int) -> bytes:
    decoded = bytearray()
    index = 0
    while index < len(data):
        length = data[index]
        index += 1
        if length == 128:
            break
        if length < 128:
            count = length + 1
            decoded.extend(data[index : index + count])
            index += count
        else:
            if index >= len(data):
                raise ValueError("Malformed PDF RunLength stream")
            decoded.extend(data[index : index + 1] * (257 - length))
            index += 1
        _require_within(decoded, remaining, limit)
    return bytes(decoded)


def _require_within(data: bytes | bytearray, remaining: int, limit: int) -> None:
    if len(data) > remaining:
        raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
