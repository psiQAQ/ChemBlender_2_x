"""Fast, cancellable SHA-256 for source snapshots."""

import hashlib
import os
from pathlib import Path


_ONE_SHOT_LIMIT = 256 * 1024 * 1024


def _windows_sha256(data):
    import ctypes

    bcrypt = ctypes.WinDLL("bcrypt")
    open_provider = bcrypt.BCryptOpenAlgorithmProvider
    open_provider.argtypes = (
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_ulong,
    )
    open_provider.restype = ctypes.c_long
    hash_data = bcrypt.BCryptHash
    hash_data.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
    )
    hash_data.restype = ctypes.c_long
    close_provider = bcrypt.BCryptCloseAlgorithmProvider
    close_provider.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    close_provider.restype = ctypes.c_long
    bytes_pointer = ctypes.pythonapi.PyBytes_AsString
    bytes_pointer.argtypes = (ctypes.py_object,)
    bytes_pointer.restype = ctypes.c_void_p

    provider = ctypes.c_void_p()
    status = open_provider(ctypes.byref(provider), "SHA256", None, 0)
    if status < 0:
        raise OSError(f"BCryptOpenAlgorithmProvider failed: {status}")
    try:
        digest = (ctypes.c_ubyte * 32)()
        status = hash_data(
            provider,
            None,
            0,
            bytes_pointer(data),
            len(data),
            digest,
            len(digest),
        )
        if status < 0:
            raise OSError(f"BCryptHash failed: {status}")
        return bytes(digest).hex()
    finally:
        close_provider(provider, 0)


def sha256_bytes(data):
    if type(data) is not bytes:
        raise TypeError("data must be bytes")
    if os.name == "nt" and len(data) <= 0xFFFFFFFF:
        try:
            return _windows_sha256(data)
        except OSError:
            pass
    return hashlib.sha256(data).hexdigest()


def sha256_file_snapshot(path, is_cancelled, *, prefix_bytes=0):
    path = Path(path)
    if not callable(is_cancelled):
        raise TypeError("is_cancelled must be callable")
    if (
        isinstance(prefix_bytes, bool)
        or not isinstance(prefix_bytes, int)
        or prefix_bytes < 0
    ):
        raise ValueError("prefix_bytes must be a non-negative integer")
    if is_cancelled():
        raise InterruptedError("source hashing was cancelled")

    # ponytail: one-shot CNG is fastest through 256 MiB; stream larger files.
    if os.name == "nt" and path.stat().st_size <= _ONE_SHOT_LIMIT:
        chunks = []
        with path.open("rb") as stream:
            while chunk := stream.read(65536):
                chunks.append(chunk)
                if is_cancelled():
                    raise InterruptedError("source hashing was cancelled")
        data = b"".join(chunks)
        return sha256_bytes(data), len(data), data[:prefix_bytes]

    digest = hashlib.sha256()
    size = 0
    prefix = bytearray()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if is_cancelled():
                raise InterruptedError("source hashing was cancelled")
            digest.update(chunk)
            size += len(chunk)
            if len(prefix) < prefix_bytes:
                prefix.extend(chunk[: prefix_bytes - len(prefix)])
    if is_cancelled():
        raise InterruptedError("source hashing was cancelled")
    return digest.hexdigest(), size, bytes(prefix)


def sha256_file(path, is_cancelled=lambda: False):
    digest, _size, _prefix = sha256_file_snapshot(path, is_cancelled)
    return digest


__all__ = ("sha256_bytes", "sha256_file", "sha256_file_snapshot")
