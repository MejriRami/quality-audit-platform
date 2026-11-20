"""Expired certificate notifications.

When a certification whose document type is "certificate" is past its
expiration date, its plant's quality manager is asked to upload the renewed
one, with the certification owner in copy (CERTIFICATION_EXPIRY_CC). Each
expiry is notified once: `expiry_notified_for` records the expiration date
the email went out for, so a renewed certificate that later expires is
notified again.

The daily job only sends when CERTIFICATION_EXPIRY_EMAILS_ENABLED is true;
`notify_expired_certificates(dry_run=True)` lists what would be sent.
"""

from __future__ import annotations

import html
import logging
import os
from datetime import date
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config.database import SessionLocal
from app.models.org_directory_member import OrgDirectoryMember
from app.services import external_certification_service as certs
from app.services.email_delivery_service import send_email_sync_tracked

logger = logging.getLogger(__name__)

DEFAULT_CC = "robin.faure@example.com"


def emails_enabled() -> bool:
    return os.getenv("CERTIFICATION_EXPIRY_EMAILS_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


def _cc_list() -> list[str]:
    raw = os.getenv("CERTIFICATION_EXPIRY_CC", DEFAULT_CC)
    return [e.strip() for e in raw.split(",") if e.strip()]


def _expired_certificates() -> list[dict]:
    with certs._connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, certification_number, certification_type, plant, "
                "quality_manager_name, quality_manager_email, certification_expiration_date "
                "FROM certifications "
                "WHERE document_type = 'certificate' "
                "AND certification_expiration_date < CURRENT_DATE "
                "AND expiry_notified_for IS DISTINCT FROM certification_expiration_date "
                "ORDER BY certification_expiration_date, id"
            )
        ).mappings().all()
    return [dict(r) for r in rows]


def _resolve_quality_manager_email(db: Session, cert: dict) -> Optional[str]:
    """The stored email, else a name field that is itself an email (rows
    migrated from Monday do this), else an exact name match in the Northwind
    directory."""
    for value in (cert.get("quality_manager_email"), cert.get("quality_manager_name")):
        value = (value or "").strip()
        if "@" in value and " " not in value and "," not in value:
            return value
    name = (cert.get("quality_manager_name") or "").strip()
    if not name or "@" in name:
        return None
    member = (
        db.query(OrgDirectoryMember.email)
        .filter(
            OrgDirectoryMember.is_active.is_(True),
            func.lower(OrgDirectoryMember.full_name) == name.lower(),
        )
        .first()
    )
    return member.email if member else None


def _email_body(cert: dict, qm_email: Optional[str]) -> str:
    esc = lambda v: html.escape(str(v)) if v else "—"  # noqa: E731
    # The public portal: most quality managers have no app account.
    link = f"{os.getenv('FRONTEND_URL', '').rstrip('/')}/certifications-portal"
    missing = (
        ""
        if qm_email
        else (
            "<p><strong>No email was found for the quality manager "
            f"({esc(cert.get('quality_manager_name'))}).</strong> Please forward this "
            "message and add their email to the certification.</p>"
        )
    )
    return f"""
<p>Hello {esc(cert.get('quality_manager_name'))},</p>
<p>The following certificate expired on
<strong>{esc(cert['certification_expiration_date'])}</strong>.
Please upload the new certificate in the Audit Management application.</p>
<table cellpadding="4" style="border-collapse:collapse">
  <tr><td><b>Certificate</b></td><td>{esc(cert.get('name'))}</td></tr>
  <tr><td><b>Number</b></td><td>{esc(cert.get('certification_number'))}</td></tr>
  <tr><td><b>Standard</b></td><td>{esc(cert.get('certification_type'))}</td></tr>
  <tr><td><b>Plant</b></td><td>{esc(cert.get('plant'))}</td></tr>
  <tr><td><b>Expired on</b></td><td>{esc(cert['certification_expiration_date'])}</td></tr>
</table>
{missing}
<p><a href="{html.escape(link)}">Open External Certifications</a></p>
<p>This is an automatic message from the Audit Management application.</p>
"""


def _mark_notified(cert_id: int, expiration: date) -> None:
    with certs._connect(commit=True) as conn:
        conn.execute(
            text("UPDATE certifications SET expiry_notified_for = :d WHERE id = :id"),
            {"d": expiration, "id": cert_id},
        )


def notify_expired_certificates(dry_run: bool = False) -> list[dict]:
    """Email the quality manager of each newly expired certificate (CC the
    certification owner). Returns one entry per certificate."""
    cc = _cc_list()
    results: list[dict] = []
    db = SessionLocal()
    try:
        for cert in _expired_certificates():
            qm_email = _resolve_quality_manager_email(db, cert)
            to = [qm_email] if qm_email else cc
            entry = {
                "certification_id": cert["id"],
                "name": cert["name"],
                "plant": cert["plant"],
                "expired_on": cert["certification_expiration_date"],
                "quality_manager": cert["quality_manager_name"],
                "to": to,
                "cc": cc if qm_email else [],
                "quality_manager_email_found": bool(qm_email),
                "sent": False,
            }
            if not dry_run and to:
                entry["sent"] = send_email_sync_tracked(
                    subject=f"Certificate expired - please upload the new one: {cert['name']}",
                    recipients=to,
                    cc=entry["cc"],
                    body_html=_email_body(cert, qm_email),
                    db=db,
                    context="certification_expiry",
                )
                if entry["sent"]:
                    _mark_notified(cert["id"], cert["certification_expiration_date"])
            results.append(entry)
    finally:
        db.close()
    return results


def run_certification_expiry_job() -> None:
    """Daily scheduler entry point."""
    if not emails_enabled():
        logger.info("Certification expiry emails disabled (CERTIFICATION_EXPIRY_EMAILS_ENABLED)")
        return
    try:
        results = notify_expired_certificates()
        logger.info(
            "Certification expiry emails: %s sent of %s",
            sum(r["sent"] for r in results),
            len(results),
        )
    except Exception:
        logger.exception("Certification expiry job failed")
