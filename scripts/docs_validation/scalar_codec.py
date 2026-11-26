"""Decode and encode the tagged JSON scalars used by the example documents.

The documents in `spec/` record I64, F64, and Bool values through JSON, which
cannot carry signed zeros, NaN payloads, or 64-bit integers faithfully. Wide
I64 values are tagged ``{"i64": "<decimal>"}`` and F64 values are tagged
``{"f64": "<decimal>"}`` or ``{"f64_bits": "<hex>"}``; plain integers and
booleans are I64 and Bool.

The codec lives here rather than inside the evaluating module so that every
documentation model which reads a tagged value shares one decoder instead of
re-deriving the tag vocabulary. Only the documentation-pack models may import
it; it is not a general JSON reader.
"""
from __future__ import annotations

import math
import struct

from .context import require


def decode(value: object) -> object:
    """Decode a tagged JSON scalar or list; e.g. {'f64': '-0.0'} becomes -0.0."""
    if isinstance(value, list):
        return [decode(item) for item in value]
    if isinstance(value, dict):
        (tag, text), = value.items()
        if tag == 'f64':
            return float(text)
        if tag == 'f64_bits':
            return struct.unpack('>d', int(text, 16).to_bytes(8, 'big'))[0]
        require(tag == 'i64', f'Unknown scalar tag {tag}')
        return int(text)
    return value


def encode(value: object) -> object:
    """Encode a model value so floats compare by bits; e.g. -0.0 becomes {'f64': '-0.0'}."""
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value):
            return {'f64_bits': f"0x{struct.unpack('>Q', struct.pack('>d', value))[0]:016x}"}
        return {'f64': repr(value)}
    return value
