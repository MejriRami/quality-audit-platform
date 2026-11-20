# app/api/routes/audit_result_email.py

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

# ✅ adjust to your project
from app.config.database import get_db
from app.models.audit import Audit  # adjust import
from app.utils.send_car_email import send_email

router = APIRouter(prefix="/audits", tags=["Audit Result Email"])


class SendAuditResultEmailPayload(BaseModel):
    # Optional if you always send to auditee from DB
    to: EmailStr | None = None
    cc: list[EmailStr] | None = None


class SendAuditResultEmailResponse(BaseModel):
    status: str


def build_audit_result_email_html(audit: Audit) -> str:
    """
    Minimal HTML inspired by your Excel structure.
    Replace audit.<field> with your real fields.
    """
    supplier = getattr(audit, "supplier_name", "--") or "--"
    order_no = getattr(audit, "order_no", "--") or "--"
    eg = getattr(audit, "eg_percent", None)
    rating = getattr(audit, "rating", "--") or "--"

    summary = getattr(audit, "summary", "") or ""
    strengths = getattr(audit, "strengths", "") or ""
    opportunities = getattr(audit, "opportunities", "") or ""

    eg_str = f"{float(eg):.0f}%" if eg is not None else "n.e."

    return f"""
<!doctype html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;background:#f6f7f9;padding:20px;">
  <div style="max-width:900px;margin:auto;background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;">
    <div style="background:#0f172a;color:#fff;padding:16px 20px;">
      <div style="font-size:18px;font-weight:700;">Audit report VDA 6.3 — Evaluation of quality capability</div>
      <div style="font-size:13px;opacity:.9;margin-top:6px;">
        Supplier: {supplier} • Order No.: {order_no}
      </div>
    </div>

    <div style="padding:18px 20px;">
      <div style="display:flex;gap:12px;flex-wrap:wrap;">
        <div style="flex:1;min-width:220px;border:1px solid #e2e8f0;border-radius:10px;padding:14px;">
          <div style="font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;">Audit result</div>
          <div style="margin-top:8px;font-size:34px;font-weight:800;">{eg_str}</div>
          <div style="margin-top:4px;font-size:14px;font-weight:700;">Rating: {rating}</div>
        </div>
        <div style="flex:2;min-width:260px;border:1px solid #e2e8f0;border-radius:10px;padding:14px;">
          <div style="font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;">Summary</div>
          <div style="margin-top:8px;white-space:pre-wrap;line-height:1.5;">{summary}</div>
        </div>
      </div>

      <div style="margin-top:14px;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;">
        <div style="background:#f8fafc;padding:10px 14px;font-weight:800;font-size:12px;">
          Significant findings
        </div>
        <div style="padding:14px;display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div style="border:1px solid #eef2f7;border-radius:8px;padding:12px;">
            <div style="font-weight:800;margin-bottom:6px;">Strengths</div>
            <div style="white-space:pre-wrap;line-height:1.5;">{strengths}</div>
          </div>
          <div style="border:1px solid #eef2f7;border-radius:8px;padding:12px;">
            <div style="font-weight:800;margin-bottom:6px;">Opportunities for Improvement</div>
            <div style="white-space:pre-wrap;line-height:1.5;">{opportunities}</div>
          </div>
        </div>
      </div>

      <div style="margin-top:14px;font-size:12px;color:#64748b;">
        Classification scale: A = 90–100% • B ≥80–&lt;90% • C &lt;80%
      </div>
    </div>

    <div style="background:#f8fafc;border-top:1px solid #e5e7eb;padding:12px 20px;font-size:12px;color:#475569;">
      This email was generated automatically from the audit result page.
    </div>
  </div>
</body>
</html>
"""


@router.post(
    "/{audit_id}/send-result-email",
    response_model=SendAuditResultEmailResponse,
    status_code=status.HTTP_200_OK,
)
async def send_result_email_endpoint(
    audit_id: int,
    payload: SendAuditResultEmailPayload,
    db: Session = Depends(get_db),
):
    # 1) load audit
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    # 2) get recipient
    # If frontend sends "to" use it; else default to auditee email stored in DB
    auditee_email = payload.to or getattr(audit, "auditee_email", None)
    if not auditee_email:
        raise HTTPException(status_code=400, detail="Auditee email not found (provide payload.to or store auditee_email in audit)")

    # 3) build email
    html = build_audit_result_email_html(audit)
    supplier = getattr(audit, "supplier_name", "Supplier")
    eg = getattr(audit, "eg_percent", None)
    rating = getattr(audit, "rating", "--")
    eg_str = f"{float(eg):.0f}%" if eg is not None else "n.e."
    subject = f"Audit report VDA 6.3 — {supplier} — {eg_str} ({rating})"

    # 4) send
    try:
        await send_email(
            subject=subject,
            recipients=[auditee_email],
            body_html=html,
            cc=[str(x) for x in (payload.cc or [])] or None,
            db=db,
            context="audit_result",
        )
        return {"status": "Email sent successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
