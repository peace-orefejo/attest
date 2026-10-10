"""Bounded decoding of PDF stream filters, refusing filters that cannot be bounded."""

from __future__ import annotations

import base64
import zlib


def bounded_pdf_decode(stream, remaining: int, limit: int) -> bytes:
    filters = stream.get("/Filter")
    if filters is None:
        names: list[str] = []
    else:
        resolved_filters = filters.get_object()
        names = ([str(item) for item in resolved_filters]
                 if isinstance(resolved_filters, list) else [str(resolved_filters)])
    data = stream._data
    for name in names:
        if name in {"/ASCII85Decode", "/A85"}:
            data = base64.a85decode(data, adobe=True)
        elif name in {"/ASCIIHexDecode", "/AHx"}:
            compact = b"".join(data.split()).removesuffix(b">")
            if len(compact) % 2:
                compact += b"0"
            data = bytes.fromhex(compact.decode("ascii"))
        elif name in {"/FlateDecode", "/Fl"}:
            decoder = zlib.decompressobj()
            data = decoder.decompress(data, remaining + 1)
            if len(data) > remaining or not decoder.eof:
                raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
        elif name in {"/RunLengthDecode", "/RL"}:
            data = _bounded_run_length_decode(data, remaining, limit)
        else:
            raise ValueError(f"PDF content filter cannot be bounded safely: {name}")
        if len(data) > remaining:
            raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
    if len(data) > remaining:
        raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
    return data


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
            decoded.extend(data[index:index + count])
            index += count
        else:
            if index >= len(data):
                raise ValueError("Malformed PDF RunLength stream")
            decoded.extend(data[index:index + 1] * (257 - length))
            index += 1
        if len(decoded) > remaining:
            raise ValueError(f"PDF decoded content exceeds {limit} byte limit")
    return bytes(decoded)
