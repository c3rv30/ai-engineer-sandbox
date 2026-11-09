"""Handling of the file name the client sends on ingestion (SEC-04).

Kept out of src/api/routers/ingest.py so it can be checked without importing the
ingestion engine, which loads models and clients at import time (BUG-07).
"""
import os


def source_name(filename: str) -> str:
    """Name under which the origin of an uploaded document is recorded.

    The client controls the name: it is reduced to its last component, with both '/'
    and '\\' separators, so that no '../' or absolute path reaches the metadata. It is
    never used as a path on disk.
    """
    return os.path.basename(filename.replace("\\", "/"))
