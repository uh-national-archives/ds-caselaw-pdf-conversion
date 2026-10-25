"""Fail-closed validation before conversion of judicial source documents."""

import re
import zipfile
from pathlib import Path
from urllib.parse import unquote_plus


MAX_DOCX_BYTES = 30 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
ETAG_PATTERN = re.compile(r"[a-fA-F0-9]{32}(?:-[1-9][0-9]*)?\Z")


class DocumentRejected(ValueError):
    """Source event or downloaded content is not safe to convert."""


def checked_source_key(value):
    if not isinstance(value, str):
        raise DocumentRejected("Missing S3 source key")
    key = unquote_plus(value)
    parts = key.split("/")
    if (
        not key
        or key.startswith("/")
        or "\\" in key
        or any(not part or part in {".", ".."} for part in parts)
        or not key.lower().endswith(".docx")
    ):
        raise DocumentRejected("Invalid DOCX source key")
    return key


def checked_etag(value):
    if not isinstance(value, str):
        raise DocumentRejected("Missing S3 object ETag")
    etag = value.strip('"')
    if not ETAG_PATTERN.fullmatch(etag):
        raise DocumentRejected("Invalid S3 object ETag")
    return etag


def validate_docx_file(filename):
    source = Path(filename)
    if not source.is_file() or not (0 < source.stat().st_size <= MAX_DOCX_BYTES):
        raise DocumentRejected("DOCX file missing, empty, or oversized")
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            filenames = {member.filename for member in members}
            if "[Content_Types].xml" not in filenames or "word/document.xml" not in filenames:
                raise DocumentRejected("File is not a WordprocessingML DOCX")
            if sum(member.file_size for member in members) > MAX_UNCOMPRESSED_BYTES:
                raise DocumentRejected("DOCX exceeds the uncompressed size limit")
            for member in members:
                parts = member.filename.split("/")
                if member.filename.startswith("/") or any(part == ".." for part in parts):
                    raise DocumentRejected("DOCX contains an unsafe archive member")
            if archive.testzip() is not None:
                raise DocumentRejected("DOCX contains a damaged archive member")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise DocumentRejected("File is not a valid DOCX archive") from exc
