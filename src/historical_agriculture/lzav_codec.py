"""LZAV (format 3) through ctypes; the shared library is compiled from tools/lzav on first use."""
from pathlib import Path
import ctypes
import hashlib
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/"tools/lzav"
_lib = None


def library():
    global _lib
    if _lib is None:
        key = hashlib.sha256((SOURCE/"lzav.h").read_bytes()+(SOURCE/"lzav_shim.c").read_bytes()).hexdigest()[:16]
        path = ROOT/f"artifacts/cache/lzav/liblzav_{key}.so"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["cc", "-O2", "-shared", "-fPIC", "-o", str(path), str(SOURCE/"lzav_shim.c")], check=True)
        _lib = ctypes.CDLL(str(path))
    return _lib


def compress(data: bytes) -> bytes:
    lib = library()
    out = ctypes.create_string_buffer(lib.wb_lzav_bound(len(data)))
    n = lib.wb_lzav_compress(data, out, len(data), len(out))
    if n <= 0: raise ValueError("LZAV compression failed")
    return out.raw[:n]


def decompress(data: bytes, size: int) -> bytes:
    out = ctypes.create_string_buffer(size)
    n = library().wb_lzav_decompress(data, out, len(data), size)
    if n != size: raise ValueError(f"LZAV decompression failed ({n})")
    return out.raw
