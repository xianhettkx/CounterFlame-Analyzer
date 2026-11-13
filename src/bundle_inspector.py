"""Read-only Unity AssetBundle header identification helpers."""
from __future__ import annotations

from typing import BinaryIO


KNOWN_SIGNATURES = (b"UnityFS", b"UnityRaw", b"UnityWeb", b"UnityArchive")


def inspect_header(stream: BinaryIO) -> dict[str, object]:
    """Read a small prefix and classify common Unity bundle signatures.

    This is a header check only. It does not decompress or decode bundle assets.
    """
    prefix = stream.read(64)
    signature = next((s for s in KNOWN_SIGNATURES if prefix.startswith(s)), None)
    if signature is None:
        return {
            "signature": None,
            "format": "unknown_or_nonstandard",
            "header_hex": prefix[:16].hex(),
        }

    remainder = prefix[len(signature):]
    version = None
    if remainder.startswith(b"\\x00"):
        remainder = remainder[1:]
    if remainder:
        candidate = remainder.split(b"\\x00", 1)[0]
        try:
            decoded = candidate.decode("ascii")
            if decoded and all(ch.isprintable() for ch in decoded):
                version = decoded
        except UnicodeDecodeError:
            pass

    return {
        "signature": signature.decode("ascii"),
        "format": signature.decode("ascii"),
        "unity_version_hint": version,
        "header_hex": prefix[:16].hex(),
    }
