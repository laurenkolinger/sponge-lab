"""The video source of a project: which S3 bucket and folder the app reads.

The choice lives in ``project.json`` in the data folder. The app reads it once at
start, so changing the source restarts the server.
"""

import http.client
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional
from xml.etree import ElementTree

PROJECT_FILE = "project.json"
PROBE_TIMEOUT_SECONDS = 15
MAX_LISTING_BYTES = 5 * 1024 * 1024
MAX_FOLDER_LENGTH = 512
FOLDER_PATTERN = re.compile(r"[^/\s][^\x00-\x1f\x7f]*/")
S3_NAMESPACE = re.compile(r"^\{[^}]*\}")


def read_project(data_dir: Path) -> Optional[Dict[str, str]]:
    """Read the saved video source.

    Args:
        data_dir: The data folder.

    Returns:
        ``{"bucket_url", "folder"}``, or None when no valid choice is saved. A damaged
        file counts as no choice, so the app still starts and asks again.
    """
    try:
        stored = json.loads((Path(data_dir) / PROJECT_FILE).read_text(encoding="utf-8"))
        return {"bucket_url": validate_bucket_url(stored["bucket_url"]), "folder": validate_folder(stored["folder"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_project(data_dir: Path, bucket_url: str, folder: str) -> None:
    """Save the video source through a temporary file, so a reader always sees a whole one.

    Args:
        data_dir: The data folder.
        bucket_url: The validated bucket URL.
        folder: The validated folder.

    Raises:
        OSError: When the file cannot be written.
    """
    target = Path(data_dir) / PROJECT_FILE
    handle, temp_name = tempfile.mkstemp(prefix=f".{PROJECT_FILE}.", dir=target.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump({"bucket_url": bucket_url, "folder": folder}, out, indent=2)
        os.replace(temp_name, target)
    except OSError:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise


def validate_bucket_url(value: Any) -> str:
    """Check a bucket URL.

    Args:
        value: The candidate.

    Returns:
        The URL with no trailing slash.

    Raises:
        ValueError: Starting with ``bucket_url:`` for anything but an http or https URL with a host.
    """
    if not isinstance(value, str):
        raise ValueError(f"bucket_url: expected text, got {type(value).__name__}")
    url = value.strip().rstrip("/")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or "?" in url or "#" in url or re.search(r"\s", url):
        raise ValueError(f"bucket_url: expected an http or https address, got {value!r}")
    return url


def validate_folder(value: Any) -> str:
    """Check a folder inside a bucket.

    Args:
        value: The candidate, with or without its trailing slash.

    Returns:
        The folder with one trailing slash.

    Raises:
        ValueError: Starting with ``folder:`` for an empty, overlong, or unsafe folder.
    """
    if not isinstance(value, str):
        raise ValueError(f"folder: expected text, got {type(value).__name__}")
    folder = value.strip().strip("/") + "/"
    segments = folder[:-1].split("/")
    if (
        len(folder) > MAX_FOLDER_LENGTH
        or not FOLDER_PATTERN.fullmatch(folder)
        or any(segment in ("", ".", "..") for segment in segments)
    ):
        raise ValueError(f"folder: expected a folder path such as videos/2024/, got {value!r}")
    return folder


def probe_bucket(bucket_url: str, folder: str) -> None:
    """Confirm that a bucket lists something in a folder.

    Args:
        bucket_url: The validated bucket URL.
        folder: The validated folder.

    Raises:
        ValueError: Starting with ``bucket_url:`` when the bucket cannot be read, or
            ``folder:`` when the folder is empty.
    """
    query = urllib.parse.urlencode({"list-type": "2", "delimiter": "/", "max-keys": "5", "prefix": folder})
    try:
        with urllib.request.urlopen(f"{bucket_url}/?{query}", timeout=PROBE_TIMEOUT_SECONDS) as answer:
            root = ElementTree.fromstring(answer.read(MAX_LISTING_BYTES))
    except (urllib.error.URLError, http.client.HTTPException, OSError, ElementTree.ParseError, ValueError) as error:
        raise ValueError(f"bucket_url: could not list {bucket_url}: {error}") from error
    tags = {S3_NAMESPACE.sub("", item.tag) for item in root}
    if not tags & {"Contents", "CommonPrefixes"}:
        raise ValueError(f"folder: {folder} holds nothing in {bucket_url}")
