"""
Centralized Azure Blob Storage service.
Handles all file uploads/deletions for the application.

Container structure:
  audits/
    car/
      car_{car_id}_{audit_ref}_{timestamp}_{original_filename}
    answers/
      answer_{answer_id}_{timestamp}_{original_filename}
"""

import os
import logging
from datetime import datetime
from typing import Optional
from fastapi import UploadFile, HTTPException
from azure.storage.blob import BlobServiceClient, BlobClient, ContentSettings
from azure.core.exceptions import AzureError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AZURE_CONNECTION_STRING = os.getenv("AZURE_CONNECTION_STRING", "")
AZURE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "audits")

# File validation
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx"}

MIME_TYPES: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".doc":  "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls":  "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

def _parse_connection_string(conn_str: str) -> dict:
    """Parse Azure connection string into a key/value dict."""
    return dict(
        part.split("=", 1)
        for part in conn_str.split(";")
        if "=" in part
    )

def _extract_blob_name(file_url: str) -> Optional[str]:
    """
    Extract the blob path from a full Azure URL.
    e.g. https://yourstorage.blob.core.windows.net/audits/car/car_1_ref_ts_file.pdf
         → car/car_1_ref_ts_file.pdf
    """
    try:
        from urllib.parse import unquote, urlparse
        parsed = urlparse(file_url)
        parts = unquote(parsed.path).lstrip("/").split("/", 1)  # [container, blob_name]
        return parts[1] if len(parts) == 2 else None
    except Exception:
        return None


def get_fresh_doc_url(file_url: str, expiry_days: int = 7) -> str:
    """Extract blob name from stored URL and generate a fresh SAS URL."""
    blob_name = _extract_blob_name(file_url)
    if not blob_name:
        return file_url
    try:
        return get_blob_sas_url(blob_name, expiry_days=expiry_days)
    except Exception:
        return file_url
    
    
def get_blob_sas_url(blob_name: str, expiry_days: int = 7) -> str:
    """
    Generate a fresh SAS URL for an existing blob.
    Use this when serving URLs to clients (admin UI, auditee form).
    """
    import datetime as dt
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions

    parts = _parse_connection_string(AZURE_CONNECTION_STRING)
    account_name = parts.get("AccountName", "")
    account_key = parts.get("AccountKey", "")

    container = _get_container_client()
    blob_client = container.get_blob_client(blob_name)

    if not account_name or not account_key:
        return blob_client.url  # fallback

    sas_token = generate_blob_sas(
        account_name=account_name,
        account_key=account_key,
        container_name=AZURE_CONTAINER_NAME,
        blob_name=blob_name,
        permission=BlobSasPermissions(read=True),
        expiry=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=expiry_days),
    )
    return f"{blob_client.url}?{sas_token}"

def get_blob_url(blob_name: str) -> str:
    return get_blob_sas_url(blob_name, expiry_days=3650)  # 10 years for stored URLs


# ---------------------------------------------------------------------------
# Client factory  (lazy singleton)
# ---------------------------------------------------------------------------

_blob_service_client: Optional[BlobServiceClient] = None


def _get_blob_service_client() -> BlobServiceClient:
    global _blob_service_client
    if _blob_service_client is None:
        if not AZURE_CONNECTION_STRING:
            raise RuntimeError(
                "AZURE_STORAGE_CONNECTION_STRING environment variable is not set."
            )
        _blob_service_client = BlobServiceClient.from_connection_string(
            AZURE_CONNECTION_STRING
        )
    return _blob_service_client


def _get_container_client():
    client = _get_blob_service_client()
    container = client.get_container_client(AZURE_CONTAINER_NAME)
    # Ensure container exists (idempotent)
    try:
        container.get_container_properties()
    except Exception:
        container.create_container()
    return container


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_blob_name(folder: str, filename: str) -> str:
    """
    Returns a blob path like:  car/car_12_AUD-2025-001_20250101_120000_report.pdf
    Always uses forward slashes (Azure convention).
    """
    return f"{folder}/{filename}"


def _safe_filename(original: str) -> str:
    """Strip path separators and whitespace from a filename."""
    import re
    from urllib.parse import unquote

    original = unquote(original)
    name = os.path.basename(original).strip()
    # Replace spaces and problematic chars with underscores
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "file"


def _validate_extension(filename: str) -> str:
    """Return lowercased extension or raise 400."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{ext}' is not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )
    return ext


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def upload_car_document(
    file: UploadFile,
    car_id: int,
    audit_ref: str = "",
) -> dict:
    """
    Upload a document for a Corrective Action Report.

    Blob path:  car/car_{car_id}_{audit_ref}_{timestamp}_{safe_filename}

    Returns a dict with:
        blob_name   – full blob path inside the container
        file_url    – public/SAS URL to the blob
        filename    – original filename (sanitised)
        mimetype    – detected MIME type
        size        – file size in bytes
    """
    return await _upload_file(
        file=file,
        folder="car",
        prefix=f"car_{car_id}_{audit_ref or 'noref'}",
    )


async def upload_answer_document(
    file: UploadFile,
    answer_id: int,
    audit_ref: str = "",
) -> dict:
    """
    Upload a document for an Audit Answer.

    Blob path:  answers/answer_{answer_id}_{audit_ref}_{timestamp}_{safe_filename}
    """
    return await _upload_file(
        file=file,
        folder="answers",
        prefix=f"answer_{answer_id}_{audit_ref or 'noref'}",
    )


async def upload_misc_document(
    file: UploadFile,
    purpose: str = "draft",
) -> dict:
    """
    Upload a document not yet tied to a final entity id.
    Useful for draft evidence uploads from UI.
    """
    safe_purpose = "".join(ch for ch in purpose if ch.isalnum() or ch in ("_", "-")) or "misc"
    return await _upload_file(
        file=file,
        folder="answers",
        prefix=f"{safe_purpose}",
    )


async def delete_blob(blob_name: str) -> bool:
    """
    Delete a blob by its full path inside the container.
    Returns True if deleted, False if not found.
    """
    try:
        container = _get_container_client()
        blob_client: BlobClient = container.get_blob_client(blob_name)
        blob_client.delete_blob()
        logger.info("Deleted blob: %s", blob_name)
        return True
    except AzureError as exc:
        if "BlobNotFound" in str(exc) or "404" in str(exc):
            logger.warning("Blob not found (already deleted?): %s", blob_name)
            return False
        logger.error("Error deleting blob %s: %s", blob_name, exc)
        raise HTTPException(status_code=500, detail=f"Error deleting file: {exc}")


def delete_blob_sync(blob_name: str) -> bool:
    """
    Synchronous variant for service layers that are not async.
    Returns True if deleted, False if not found.
    """
    try:
        container = _get_container_client()
        blob_client: BlobClient = container.get_blob_client(blob_name)
        blob_client.delete_blob()
        logger.info("Deleted blob: %s", blob_name)
        return True
    except AzureError as exc:
        if "BlobNotFound" in str(exc) or "404" in str(exc):
            logger.warning("Blob not found (already deleted?): %s", blob_name)
            return False
        logger.error("Error deleting blob %s: %s", blob_name, exc)
        raise HTTPException(status_code=500, detail=f"Error deleting file: {exc}")




# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def upload_bytes_sync(content: bytes, folder: str, filename: str) -> dict:
    """
    Upload server-generated bytes (e.g. a generated PDF report) without
    needing a FastAPI UploadFile — sync, for use from non-async service
    layers such as the KPI chatbot's tool-calling loop.
    """
    size = len(content)
    if size == 0:
        raise HTTPException(status_code=400, detail="Generated file is empty.")
    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Generated file too large ({size / 1_048_576:.1f} MB). Max allowed: {MAX_FILE_SIZE // 1_048_576} MB.",
        )

    safe_name = _safe_filename(filename)
    ext = os.path.splitext(safe_name)[1].lower()
    mimetype = MIME_TYPES.get(ext, "application/octet-stream")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    blob_name = _build_blob_name(folder, f"{timestamp}_{safe_name}")

    try:
        container = _get_container_client()
        blob_client: BlobClient = container.get_blob_client(blob_name)
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=mimetype),
        )
        logger.info("Uploaded blob: %s (%d bytes)", blob_name, size)
    except AzureError as exc:
        logger.error("Azure upload error for %s: %s", blob_name, exc)
        raise HTTPException(status_code=500, detail=f"File upload failed: {exc}")

    return {
        "blob_name": blob_name,
        "file_url": get_blob_url(blob_name),
        "filename": safe_name,
        "mimetype": mimetype,
        "size": size,
    }


async def _upload_file(
    file: UploadFile,
    folder: str,
    prefix: str,
) -> dict:
    """Core upload logic shared by all upload helpers."""

    # --- Validate extension ---
    original_name = _safe_filename(file.filename or "file")
    ext = _validate_extension(original_name)

    # --- Read content & validate size ---
    content = await file.read()
    size = len(content)
    if size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size / 1_048_576:.1f} MB). Max allowed: {MAX_FILE_SIZE // 1_048_576} MB.",
        )

    # --- Build unique blob name ---
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    blob_filename = f"{prefix}_{timestamp}_{original_name}"
    blob_name = _build_blob_name(folder, blob_filename)

    # --- Upload to Azure ---
    mimetype = file.content_type or MIME_TYPES.get(ext, "application/octet-stream")
    try:
        container = _get_container_client()
        blob_client: BlobClient = container.get_blob_client(blob_name)
        blob_client.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=mimetype),
        )
        logger.info("Uploaded blob: %s  (%d bytes)", blob_name, size)
    except AzureError as exc:
        logger.error("Azure upload error for %s: %s", blob_name, exc)
        raise HTTPException(status_code=500, detail=f"File upload failed: {exc}")

    file_url = get_blob_url(blob_name)

    return {
        "blob_name": blob_name,
        "file_url": file_url,
        "filename": original_name,
        "mimetype": mimetype,
        "size": size,
    }
