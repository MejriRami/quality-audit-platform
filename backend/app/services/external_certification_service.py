"""External certifications: CRUD on the `certifications` table of the
"Audit external certification" database, plus its attached documents.

Ported from the standalone certification_crud_app. The data stays in its own
database (same server and user as this app's DATABASE_URL, only the database
name differs - override with CERTIFICATIONS_DATABASE_URL), so the Monday
migration script and the audit-planning engine keep reading it unchanged.

Documents are stored as plain (private) blob URLs and signed on every read,
whatever container the URL points at - the Monday migration put some of them
outside this app's AZURE_STORAGE_CONTAINER_NAME.
"""

from __future__ import annotations

import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Iterator, Optional
from urllib.parse import unquote, urlsplit

from azure.storage.blob import BlobSasPermissions, ContentSettings, generate_blob_sas
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import DBAPIError

from app.config.database import DATABASE_URL
from app.services.blob_storage_service import _get_blob_service_client

logger = logging.getLogger(__name__)

CERTIFICATIONS_DATABASE_NAME = "Audit external certification"
DOCUMENTS_CONTAINER = "audits"
DOCUMENT_URL_MINUTES_VALID = 15

WRITABLE_COLUMNS = [
    "certification_number",
    "name",
    "certification_type",
    "document_type",
    "scope",
    "plant",
    "quality_manager_name",
    "quality_manager_email",
    "external_certification_body",
    "audit_date",
    "date_of_last_audit",
    "next_expected_audit",
    "certification_expiration_date",
    "status",
    "rejected_reason",
    "automation_status",
    "quality_manager_decision",
    "monday_group",
]

# Values allowed in certifications.document_type (see DocumentType in the router).
CERTIFICATION_DOCUMENT_TYPES = {"certificate", "report", "report.json for IATF CARA", "other"}

# Postgres enum columns need an explicit cast from a bound text parameter.
ENUM_CASTS = {"status": "certification_status", "monday_group": "audit_group"}

LIST_SELECT = """
    SELECT c.*,
           COUNT(DISTINCT nc.id) AS nonconformity_count,
           COUNT(DISTINCT doc.id) AS document_count
    FROM certifications c
    LEFT JOIN certification_nonconformities nc ON nc.certification_id = c.id
    LEFT JOIN certification_documents doc ON doc.certification_id = c.id
"""
GROUP_BY = " GROUP BY c.id"


# ─────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────


@lru_cache(maxsize=None)
def _engine() -> Engine:
    url = os.getenv("CERTIFICATIONS_DATABASE_URL") or make_url(DATABASE_URL).set(
        database=CERTIFICATIONS_DATABASE_NAME
    )
    engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=2)
    _ensure_schema(engine)
    return engine


def _ensure_schema(engine: Engine) -> None:
    """This database has no migrations, so columns added by this app are
    created here (idempotent). The planning engine selects named columns, so
    an extra column doesn't affect it."""
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE certifications ADD COLUMN IF NOT EXISTS document_type TEXT"))
            # Expiration date the "certificate expired" email was sent for, so
            # it goes once per expiry and again after a renewal expires.
            conn.execute(text("ALTER TABLE certifications ADD COLUMN IF NOT EXISTS expiry_notified_for DATE"))
    except DBAPIError:
        logger.exception("Could not add certifications columns")


@contextmanager
def _connect(commit: bool = False) -> Iterator[Connection]:
    """Yields a connection; database errors (bad enum value, constraint
    violation...) surface as a 400 with Postgres' own message, as they did in
    the standalone app."""
    try:
        with _engine().connect() as conn:
            yield conn
            if commit:
                conn.commit()
    except DBAPIError as exc:
        diag = getattr(exc.orig, "diag", None)
        message = getattr(diag, "message_primary", None) or str(exc.orig)
        raise HTTPException(status_code=400, detail=message) from exc


def _placeholder(column: str) -> str:
    cast = ENUM_CASTS.get(column)
    return f"CAST(:{column} AS {cast})" if cast else f":{column}"


# ─────────────────────────────────────────────────────────────
# Certifications
# ─────────────────────────────────────────────────────────────


def get_meta() -> dict:
    with _connect() as conn:
        statuses = conn.execute(
            text("SELECT enumlabel FROM pg_enum WHERE enumtypid = 'certification_status'::regtype ORDER BY enumsortorder")
        ).scalars().all()
        monday_groups = conn.execute(
            text("SELECT enumlabel FROM pg_enum WHERE enumtypid = 'audit_group'::regtype ORDER BY enumsortorder")
        ).scalars().all()
        plants = conn.execute(
            text("SELECT DISTINCT plant FROM certifications WHERE plant IS NOT NULL ORDER BY plant")
        ).scalars().all()
        certification_types = conn.execute(
            text(
                "SELECT DISTINCT certification_type FROM certifications "
                "WHERE certification_type IS NOT NULL ORDER BY certification_type"
            )
        ).scalars().all()
    return {
        "statuses": statuses,
        "monday_groups": monday_groups,
        "plants": plants,
        "certification_types": certification_types,
    }


def list_certifications(
    search: Optional[str] = None,
    status: Optional[str] = None,
    plant: Optional[str] = None,
    monday_group: Optional[str] = None,
) -> list[dict]:
    where: list[str] = []
    params: dict[str, Any] = {}
    if search:
        where.append("(c.name ILIKE :like OR c.certification_number ILIKE :like OR c.plant ILIKE :like)")
        params["like"] = f"%{search}%"
    if status:
        where.append("c.status = CAST(:status AS certification_status)")
        params["status"] = status
    if plant:
        where.append("c.plant = :plant")
        params["plant"] = plant
    if monday_group:
        where.append("c.monday_group = CAST(:monday_group AS audit_group)")
        params["monday_group"] = monday_group

    sql = LIST_SELECT
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += GROUP_BY + " ORDER BY c.updated_at DESC NULLS LAST, c.id DESC"

    with _connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def get_certification(cert_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute(
            text(LIST_SELECT + " WHERE c.id = :id" + GROUP_BY), {"id": cert_id}
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Certification not found")
    return dict(row)


def create_certification(data: dict) -> dict:
    columns = [c for c in WRITABLE_COLUMNS if c in data]
    sql = (
        f"INSERT INTO certifications ({', '.join(columns)}) "
        f"VALUES ({', '.join(_placeholder(c) for c in columns)}) RETURNING id"
    )
    with _connect(commit=True) as conn:
        new_id = conn.execute(text(sql), {c: data[c] for c in columns}).scalar_one()
    return get_certification(new_id)


def update_certification(cert_id: int, data: dict) -> dict:
    set_clauses = [f"{c} = {_placeholder(c)}" for c in WRITABLE_COLUMNS]
    set_clauses.append("updated_at = NOW()")
    sql = f"UPDATE certifications SET {', '.join(set_clauses)} WHERE id = :id RETURNING id"
    params = {c: data.get(c) for c in WRITABLE_COLUMNS}
    params["id"] = cert_id
    with _connect(commit=True) as conn:
        row = conn.execute(text(sql), params).first()
    if not row:
        raise HTTPException(status_code=404, detail="Certification not found")
    return get_certification(cert_id)


def delete_certification(cert_id: int) -> None:
    """Linked documents/nonconformities go with it (ON DELETE CASCADE)."""
    with _connect(commit=True) as conn:
        row = conn.execute(
            text("DELETE FROM certifications WHERE id = :id RETURNING id"), {"id": cert_id}
        ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Certification not found")


# ─────────────────────────────────────────────────────────────
# Documents
# ─────────────────────────────────────────────────────────────


def _split_blob_url(file_url: str) -> tuple[str, str]:
    container_name, _, blob_name = unquote(urlsplit(file_url).path).lstrip("/").partition("/")
    return container_name, blob_name


def sign_url(file_url: str, minutes_valid: int = DOCUMENT_URL_MINUTES_VALID) -> str:
    """Turns a stored (private-container) blob URL into a time-limited,
    directly-downloadable SAS URL."""
    service = _get_blob_service_client()
    parts = urlsplit(file_url)
    container_name, blob_name = _split_blob_url(file_url)
    sas = generate_blob_sas(
        account_name=service.account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=service.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=minutes_valid),
    )
    return f"{parts.scheme}://{parts.netloc}{parts.path}?{sas}"


def _document_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "document_type": row["document_type"],
        "filename": row["filename"],
        "uploaded_at": row["uploaded_at"],
        "download_url": sign_url(row["file_url"]),
    }


def list_documents(cert_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, document_type, filename, file_url, uploaded_at "
                "FROM certification_documents WHERE certification_id = :id "
                "ORDER BY uploaded_at DESC NULLS LAST, id"
            ),
            {"id": cert_id},
        ).mappings().all()
    return [_document_out(r) for r in rows]


def upload_document(
    cert_id: int, data: bytes, filename: Optional[str], content_type: Optional[str], document_type: Optional[str]
) -> dict:
    with _connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM certifications WHERE id = :id"), {"id": cert_id}).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Certification not found")

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "document")
    blob_path = f"external-certification/{cert_id}/{int(time.time() * 1000)}_{safe_name}"
    blob = _get_blob_service_client().get_blob_client(container=DOCUMENTS_CONTAINER, blob=blob_path)
    blob.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type) if content_type else None,
    )
    file_url = blob.url

    with _connect(commit=True) as conn:
        row = conn.execute(
            text(
                "INSERT INTO certification_documents "
                "(certification_id, document_type, filename, mimetype, size, file_url, uploaded_at) "
                "VALUES (:cert_id, :document_type, :filename, :mimetype, :size, :file_url, NOW()) "
                "RETURNING id, document_type, filename, file_url, uploaded_at"
            ),
            {
                "cert_id": cert_id,
                "document_type": document_type,
                "filename": filename,
                "mimetype": content_type,
                "size": len(data),
                "file_url": file_url,
            },
        ).mappings().one()
        # A certification without a document type takes the type of its first
        # typed upload, so the list doesn't show "—" next to uploaded files.
        if document_type in CERTIFICATION_DOCUMENT_TYPES:
            conn.execute(
                text("UPDATE certifications SET document_type = :t WHERE id = :id AND document_type IS NULL"),
                {"t": document_type, "id": cert_id},
            )
    return _document_out(dict(row))


def delete_document(cert_id: int, doc_id: int) -> None:
    with _connect(commit=True) as conn:
        row = conn.execute(
            text(
                "DELETE FROM certification_documents WHERE id = :doc_id AND certification_id = :cert_id "
                "RETURNING file_url"
            ),
            {"doc_id": doc_id, "cert_id": cert_id},
        ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    # The row is already gone; a leftover blob is harmless, so don't fail the request over it.
    container_name, blob_name = _split_blob_url(row.file_url)
    try:
        _get_blob_service_client().get_blob_client(container=container_name, blob=blob_name).delete_blob()
    except Exception:
        logger.exception("Could not delete blob for certification document %s: %s", doc_id, row.file_url)
