import hashlib
import json


def canonical_json_bytes(obj) -> bytes:
    """
    The ONE serialization that every hash of this project is made from: keys sorted, no spaces,
    ASCII only, UTF-8 bytes. NaN and Infinity are refused (they are not JSON).
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_hash(obj) -> str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()
