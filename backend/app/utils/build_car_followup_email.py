from typing import Optional, List, Dict


FRONTEND_URL = "https://your-app.azurewebsites.net"


def _build_cars_table(
    cars: List[Dict], badge_color: str, badge_bg: str, badge_border: str, show_action: bool = False
) -> str:
    """Build an HTML table rows for a list of CARs. `show_action` adds a
    "Complete Form" button column, for emails the auditee is meant to act on
    directly (each row carries its own token, so each button links to its
    own CAR - a shared "form_url" doesn't exist)."""
    rows = ""
    for i, car in enumerate(cars, 1):
        row_bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        type_colors = {
            "Critical":    "#C62828",
            "Improvement": "#0277BD",
            "Observation": "#F9A825",
        }
        badge = car.get("car_type", "Observation")
        badge_c = type_colors.get(badge, "#F9A825")
        action_cell = ""
        if show_action:
            form_url = car.get("form_url")
            action_cell = (
                f"""<td style="padding:12px;border:1px solid #e0e0e0;text-align:center;">
                <a href="{form_url}" style="display:inline-block;background:{badge_color};color:#ffffff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:700;font-size:13px;">Complete Form</a>
            </td>"""
                if form_url
                else '<td style="padding:12px;border:1px solid #e0e0e0;text-align:center;color:#999;font-size:12px;">N/A</td>'
            )
        rows += f"""
        <tr style="background:{row_bg};">
            <td style="padding:12px;border:1px solid #e0e0e0;text-align:center;font-weight:700;color:#666;">#{i}</td>
            <td style="padding:12px;border:1px solid #e0e0e0;text-align:center;">
                <span style="background:{badge_c};color:white;padding:5px 10px;border-radius:20px;font-size:11px;font-weight:700;text-transform:uppercase;">{badge}</span>
            </td>
            <td style="padding:12px;border:1px solid #e0e0e0;color:#333;line-height:1.5;">{car.get("question", "N/A")}</td>
            <td style="padding:12px;border:1px solid #e0e0e0;color:#555;line-height:1.5;">{car.get("finding", "N/A")}</td>
            <td style="padding:12px;border:1px solid #e0e0e0;text-align:center;">
                <span style="background:{badge_bg};color:{badge_color};padding:6px 10px;border-radius:6px;border:1px solid {badge_border};font-weight:700;font-size:13px;">{car.get("due_date", "N/A")}</span>
            </td>
            <td style="padding:12px;border:1px solid #e0e0e0;color:#555;font-size:13px;">{car.get("days_overdue", "N/A")} days</td>
            {action_cell}
        </tr>"""
    return rows


def _build_cars_table_with_audit(cars: List[Dict], badge_color: str, badge_bg: str, badge_border: str) -> str:
    """Same as _build_cars_table, but with Audit/Plant/Auditee columns per
    row - for digests that bundle CARs from multiple different audits into
    one email, where a single shared audit/plant/auditee header no longer
    applies to every row."""
    rows = ""
    for i, car in enumerate(cars, 1):
        row_bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        type_colors = {
            "Critical":    "#C62828",
            "Improvement": "#0277BD",
            "Observation": "#F9A825",
        }
        badge = car.get("car_type", "Observation")
        badge_c = type_colors.get(badge, "#F9A825")
        rows += f"""
        <tr style="background:{row_bg};">
            <td style="padding:12px;border:1px solid #e0e0e0;text-align:center;font-weight:700;color:#666;">#{i}</td>
            <td style="padding:12px;border:1px solid #e0e0e0;color:#333;font-weight:600;">{car.get("audit_reference", "N/A")}</td>
            <td style="padding:12px;border:1px solid #e0e0e0;color:#333;">{car.get("plant", "N/A")}</td>
            <td style="padding:12px;border:1px solid #e0e0e0;color:#333;">{car.get("auditee_name", "N/A")}</td>
            <td style="padding:12px;border:1px solid #e0e0e0;text-align:center;">
                <span style="background:{badge_c};color:white;padding:5px 10px;border-radius:20px;font-size:11px;font-weight:700;text-transform:uppercase;">{badge}</span>
            </td>
            <td style="padding:12px;border:1px solid #e0e0e0;color:#333;line-height:1.5;">{car.get("question", "N/A")}</td>
            <td style="padding:12px;border:1px solid #e0e0e0;color:#555;line-height:1.5;">{car.get("finding", "N/A")}</td>
            <td style="padding:12px;border:1px solid #e0e0e0;text-align:center;">
                <span style="background:{badge_bg};color:{badge_color};padding:6px 10px;border-radius:6px;border:1px solid {badge_border};font-weight:700;font-size:13px;">{car.get("due_date", "N/A")}</span>
            </td>
            <td style="padding:12px;border:1px solid #e0e0e0;color:#555;font-size:13px;">{car.get("days_overdue", "N/A")} days</td>
        </tr>"""
    return rows


def build_group_vp_escalation_digest_email_body(due_date: str, cars: List[Dict]) -> str:
    """VP digest: ALL CARs across ALL audits that hit day 15, bundled into
    one email per shared due date (unlike the other stages, which are
    scoped to one audit/auditee - the VP is a single fixed recipient, so
    there's no reason to split their view up by audit)."""
    audits_count = len({c.get("audit_reference") for c in cars})
    cars_table = _build_cars_table_with_audit(cars, "#4A148C", "#EDE7F6", "#7B1FA2")

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
    <body style="font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:40px 20px;margin:0;">
      <div style="max-width:1100px;margin:auto;background:white;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,0.2);overflow:hidden;">
        <div style="background:linear-gradient(135deg,#1B5E20 0%,#2E7D32 100%);padding:30px;text-align:center;">
          <h1 style="color:white;margin:0;font-size:24px;font-weight:300;letter-spacing:1px;">Quality Management System – Northwind</h1>
        </div>
        <div style="background:#EDE7F6;border-left:6px solid #7B1FA2;padding:25px 30px;">
          <h2 style="color:#4A148C;margin:0 0 8px 0;font-size:26px;font-weight:700;">🔴 Executive Escalation Digest – CARs Still Open (Day 15)</h2>
          <p style="color:#4A148C;margin:0;font-size:15px;font-weight:600;">Escalated to Group VP – Immediate Attention Required</p>
        </div>
        <div style="padding:35px 30px;">
          <p style="font-size:16px;line-height:1.8;color:#333;">Dear <strong style="color:#1B5E20;">Group Vice President</strong>,</p>
          <p style="font-size:15px;line-height:1.8;color:#555;">
            The following corrective action(s), due <strong>{due_date}</strong>, remain
            <strong style="color:#7B1FA2;">open 15 days after the due date</strong> and have not been resolved
            despite prior reminders and plant manager escalation. Your direct intervention is requested.
          </p>
          <div style="background:#f8f9fa;border-left:4px solid #1B5E20;padding:20px;margin:25px 0;border-radius:8px;">
            <p style="margin:0;font-size:15px;color:#333;line-height:1.9;">
                <strong style="color:#1B5E20;">📅 Due Date:</strong> {due_date}<br>
                <strong style="color:#1B5E20;">📂 Audits Affected:</strong> {audits_count}<br>
                <strong style="color:#1B5E20;">📊 Total Overdue Actions:</strong> {len(cars)}
            </p>
          </div>
          <h3 style="color:#4A148C;margin:30px 0 15px 0;">📋 Unresolved Corrective Actions</h3>
          <div style="overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;">
              <thead>
                <tr style="background:linear-gradient(135deg,#4A148C 0%,#7B1FA2 100%);">
                  <th style="padding:13px;color:white;text-align:center;">#</th>
                  <th style="padding:13px;color:white;text-align:left;">Audit</th>
                  <th style="padding:13px;color:white;text-align:left;">Plant</th>
                  <th style="padding:13px;color:white;text-align:left;">Auditee</th>
                  <th style="padding:13px;color:white;text-align:center;">Type</th>
                  <th style="padding:13px;color:white;text-align:left;">Question Not Answered</th>
                  <th style="padding:13px;color:white;text-align:left;">Auditor Finding</th>
                  <th style="padding:13px;color:white;text-align:center;">Due Date</th>
                  <th style="padding:13px;color:white;text-align:center;">Days Overdue</th>
                </tr>
              </thead>
              <tbody>{cars_table}</tbody>
            </table>
          </div>
          <div style="background:#EDE7F6;border-left:4px solid #7B1FA2;padding:18px;margin:28px 0;border-radius:8px;">
            <p style="margin:0;color:#4A148C;line-height:1.6;">
              🔴 <strong>Executive Action Required:</strong> These corrective actions have gone unresolved for 15+ days
              despite auditee reminders and plant manager escalation.
              Please take immediate action to ensure compliance.
            </p>
          </div>
          <p style="font-size:15px;color:#333;">Best regards,<br/><strong style="color:#1B5E20;">Quality Team – Northwind</strong></p>
        </div>
        <div style="background:#f8f9fa;padding:15px 30px;text-align:center;border-top:1px solid #e0e0e0;">
          <p style="margin:0;font-size:12px;color:#888;">Automated notification – Northwind Quality Management System</p>
        </div>
      </div>
    </body></html>"""


def _build_audit_info_block(
    audit_reference: str,
    audit_type: str,
    plant: str,
    auditee_name: str,
    supervisor_name: Optional[str] = None,
    total_cars: int = 1,
) -> str:
    supervisor_row = f'<strong style="color:#1B5E20;">Supervisor:</strong> {supervisor_name}<br>' if supervisor_name else ""
    return f"""
    <div style="background:#f8f9fa;border-left:4px solid #1B5E20;padding:20px;margin:25px 0;border-radius:8px;">
        <p style="margin:0;font-size:15px;color:#333;line-height:1.9;">
            <strong style="color:#1B5E20;">📋 Audit Reference:</strong> {audit_reference}<br>
            <strong style="color:#1B5E20;">🏭 Plant:</strong> {plant}<br>
            <strong style="color:#1B5E20;">📂 Audit Type:</strong> {audit_type}<br>
            <strong style="color:#1B5E20;">👤 Auditee:</strong> {auditee_name}<br>
            {supervisor_row}
            <strong style="color:#1B5E20;">📊 Total Overdue Actions:</strong> {total_cars}
        </p>
    </div>"""


def build_auditee_reminder_email_body(
    audit_reference: str,
    due_date: str,
    auditee_name: Optional[str] = None,
    car_identifier: Optional[str] = None,
    plant: Optional[str] = None,
    reason: Optional[str] = None,
    # New grouped fields
    cars: Optional[List[Dict]] = None,
    audit_type: Optional[str] = None,
) -> str:
    auditee_name = auditee_name or "Auditee"
    plant = plant or "N/A"
    audit_type = audit_type or "N/A"

    # Support both single CAR (legacy) and grouped CARs
    if not cars:
        cars = [{"question": "N/A", "finding": reason or "N/A", "due_date": due_date, "car_type": "Observation", "days_overdue": "N/A"}]

    cars_table = _build_cars_table(cars, "#8A4B00", "#FFF3CD", "#FFC107", show_action=True)
    audit_info = _build_audit_info_block(
        audit_reference=audit_reference,
        audit_type=audit_type,
        plant=plant,
        auditee_name=auditee_name,
        total_cars=len(cars),
    )

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
    <body style="font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:40px 20px;margin:0;">
      <div style="max-width:980px;margin:auto;background:white;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,0.2);overflow:hidden;">
        <div style="background:linear-gradient(135deg,#1B5E20 0%,#2E7D32 100%);padding:30px;text-align:center;">
          <h1 style="color:white;margin:0;font-size:24px;font-weight:300;letter-spacing:1px;">Quality Management System – Northwind</h1>
        </div>
        <div style="background:#FFF3CD;border-left:6px solid #FFC107;padding:25px 30px;">
          <h2 style="color:#8A4B00;margin:0 0 8px 0;font-size:26px;font-weight:700;">⏰ Reminder – Corrective Action(s) Overdue</h2>
          <p style="color:#8A4B00;margin:0;font-size:15px;font-weight:600;">Immediate action required</p>
        </div>
        <div style="padding:35px 30px;">
          <p style="font-size:16px;line-height:1.8;color:#333;">Dear <strong style="color:#1B5E20;">{auditee_name}</strong>,</p>
          <p style="font-size:15px;line-height:1.8;color:#555;">
            The following corrective action(s) from audit <strong>{audit_reference}</strong> are overdue and still pending.
            Please complete them immediately to avoid further escalation to management.
          </p>
          {audit_info}
          <h3 style="color:#1B5E20;margin:30px 0 15px 0;">📋 Overdue Corrective Actions</h3>
          <div style="overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;">
              <thead>
                <tr style="background:linear-gradient(135deg,#1B5E20 0%,#2E7D32 100%);">
                  <th style="padding:13px;color:white;text-align:center;">#</th>
                  <th style="padding:13px;color:white;text-align:center;">Type</th>
                  <th style="padding:13px;color:white;text-align:left;">Question</th>
                  <th style="padding:13px;color:white;text-align:left;">Finding</th>
                  <th style="padding:13px;color:white;text-align:center;">Due Date</th>
                  <th style="padding:13px;color:white;text-align:center;">Days Overdue</th>
                  <th style="padding:13px;color:white;text-align:center;">Action</th>
                </tr>
              </thead>
              <tbody>{cars_table}</tbody>
            </table>
          </div>
          <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:18px;margin:28px 0;border-radius:8px;">
            <p style="margin:0;color:#856404;line-height:1.6;">
              ⚠️ <strong>Warning:</strong> If no action is taken, this will be escalated to your Plant Manager and Group VP.
            </p>
          </div>
          <p style="font-size:15px;color:#333;">Best regards,<br/><strong style="color:#1B5E20;">Quality Team – Northwind</strong></p>
        </div>
        <div style="background:#f8f9fa;padding:15px 30px;text-align:center;border-top:1px solid #e0e0e0;">
          <p style="margin:0;font-size:12px;color:#888;">Automated notification – Northwind Quality Management System</p>
        </div>
      </div>
    </body></html>"""


def build_plant_manager_email_body(
    audit_reference: str,
    due_date: str,
    auditee_name: Optional[str] = None,
    car_identifier: Optional[str] = None,
    plant: Optional[str] = None,
    reason: Optional[str] = None,
    # New richer fields
    cars: Optional[List[Dict]] = None,
    audit_type: Optional[str] = None,
    supervisor_name: Optional[str] = None,
) -> str:
    auditee_name = auditee_name or "Auditee"
    plant = plant or "N/A"
    audit_type = audit_type or "N/A"

    if not cars:
        cars = [{"question": "N/A", "finding": reason or "N/A", "due_date": due_date, "car_type": "Observation", "days_overdue": "N/A"}]

    cars_table = _build_cars_table(cars, "#7A1E1E", "#FDECEA", "#DC3545")
    audit_info = _build_audit_info_block(
        audit_reference=audit_reference,
        audit_type=audit_type,
        plant=plant,
        auditee_name=auditee_name,
        supervisor_name=supervisor_name,
        total_cars=len(cars),
    )

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
    <body style="font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:40px 20px;margin:0;">
      <div style="max-width:980px;margin:auto;background:white;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,0.2);overflow:hidden;">
        <div style="background:linear-gradient(135deg,#1B5E20 0%,#2E7D32 100%);padding:30px;text-align:center;">
          <h1 style="color:white;margin:0;font-size:24px;font-weight:300;letter-spacing:1px;">Quality Management System – Northwind</h1>
        </div>
        <div style="background:#FDECEA;border-left:6px solid #DC3545;padding:25px 30px;">
          <h2 style="color:#7A1E1E;margin:0 0 8px 0;font-size:26px;font-weight:700;">🚨 Escalation – CAR Still Open (Day 11)</h2>
          <p style="color:#7A1E1E;margin:0;font-size:15px;font-weight:600;">Escalated to Plant Manager – Action Required</p>
        </div>
        <div style="padding:35px 30px;">
          <p style="font-size:16px;line-height:1.8;color:#333;">Dear <strong style="color:#1B5E20;">Plant Manager</strong>,</p>
          <p style="font-size:15px;line-height:1.8;color:#555;">
            The following corrective action(s) assigned to <strong>{auditee_name}</strong> from audit
            <strong>{audit_reference}</strong> remain <strong style="color:#DC3545;">open 11 days after the due date</strong>.
            Your intervention is required to ensure timely resolution.
          </p>
          {audit_info}
          <h3 style="color:#C62828;margin:30px 0 15px 0;">📋 Unresolved Corrective Actions</h3>
          <div style="overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;">
              <thead>
                <tr style="background:linear-gradient(135deg,#C62828 0%,#DC3545 100%);">
                  <th style="padding:13px;color:white;text-align:center;">#</th>
                  <th style="padding:13px;color:white;text-align:center;">Type</th>
                  <th style="padding:13px;color:white;text-align:left;">Question Not Answered</th>
                  <th style="padding:13px;color:white;text-align:left;">Auditor Finding</th>
                  <th style="padding:13px;color:white;text-align:center;">Due Date</th>
                  <th style="padding:13px;color:white;text-align:center;">Days Overdue</th>
                </tr>
              </thead>
              <tbody>{cars_table}</tbody>
            </table>
          </div>
          <div style="background:#FDECEA;border-left:4px solid #DC3545;padding:18px;margin:28px 0;border-radius:8px;">
            <p style="margin:0;color:#7A1E1E;line-height:1.6;">
              🚨 <strong>Action Required:</strong> Please follow up with <strong>{auditee_name}</strong> immediately.
              If unresolved, this will be escalated to the Group VP on Day 15.
            </p>
          </div>
          <p style="font-size:15px;color:#333;">Best regards,<br/><strong style="color:#1B5E20;">Quality Team – Northwind</strong></p>
        </div>
        <div style="background:#f8f9fa;padding:15px 30px;text-align:center;border-top:1px solid #e0e0e0;">
          <p style="margin:0;font-size:12px;color:#888;">Automated notification – Northwind Quality Management System</p>
        </div>
      </div>
    </body></html>"""


def build_group_vp_escalation_email_body(
    audit_reference: str,
    due_date: str,
    auditee_name: Optional[str] = None,
    car_identifier: Optional[str] = None,
    plant: Optional[str] = None,
    reason: Optional[str] = None,
    # New richer fields
    cars: Optional[List[Dict]] = None,
    audit_type: Optional[str] = None,
    supervisor_name: Optional[str] = None,
) -> str:
    auditee_name = auditee_name or "Auditee"
    plant = plant or "N/A"
    audit_type = audit_type or "N/A"

    if not cars:
        cars = [{"question": "N/A", "finding": reason or "N/A", "due_date": due_date, "car_type": "Observation", "days_overdue": "N/A"}]

    cars_table = _build_cars_table(cars, "#4A148C", "#EDE7F6", "#7B1FA2")
    audit_info = _build_audit_info_block(
        audit_reference=audit_reference,
        audit_type=audit_type,
        plant=plant,
        auditee_name=auditee_name,
        supervisor_name=supervisor_name,
        total_cars=len(cars),
    )

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
    <body style="font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:40px 20px;margin:0;">
      <div style="max-width:980px;margin:auto;background:white;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,0.2);overflow:hidden;">
        <div style="background:linear-gradient(135deg,#1B5E20 0%,#2E7D32 100%);padding:30px;text-align:center;">
          <h1 style="color:white;margin:0;font-size:24px;font-weight:300;letter-spacing:1px;">Quality Management System – Northwind</h1>
        </div>
        <div style="background:#EDE7F6;border-left:6px solid #7B1FA2;padding:25px 30px;">
          <h2 style="color:#4A148C;margin:0 0 8px 0;font-size:26px;font-weight:700;">🔴 Executive Escalation – CAR Still Open (Day 15)</h2>
          <p style="color:#4A148C;margin:0;font-size:15px;font-weight:600;">Escalated to Group VP – Immediate Attention Required</p>
        </div>
        <div style="padding:35px 30px;">
          <p style="font-size:16px;line-height:1.8;color:#333;">Dear <strong style="color:#1B5E20;">Group Vice President</strong>,</p>
          <p style="font-size:15px;line-height:1.8;color:#555;">
            The following corrective action(s) assigned to <strong>{auditee_name}</strong> from audit
            <strong>{audit_reference}</strong> remain <strong style="color:#7B1FA2;">open 15 days after the due date</strong>
            and have not been resolved despite prior reminders and plant manager escalation.
            Your direct intervention is requested.
          </p>
          {audit_info}
          <h3 style="color:#4A148C;margin:30px 0 15px 0;">📋 Unresolved Corrective Actions</h3>
          <div style="overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;">
              <thead>
                <tr style="background:linear-gradient(135deg,#4A148C 0%,#7B1FA2 100%);">
                  <th style="padding:13px;color:white;text-align:center;">#</th>
                  <th style="padding:13px;color:white;text-align:center;">Type</th>
                  <th style="padding:13px;color:white;text-align:left;">Question Not Answered</th>
                  <th style="padding:13px;color:white;text-align:left;">Auditor Finding</th>
                  <th style="padding:13px;color:white;text-align:center;">Due Date</th>
                  <th style="padding:13px;color:white;text-align:center;">Days Overdue</th>
                </tr>
              </thead>
              <tbody>{cars_table}</tbody>
            </table>
          </div>
          <div style="background:#EDE7F6;border-left:4px solid #7B1FA2;padding:18px;margin:28px 0;border-radius:8px;">
            <p style="margin:0;color:#4A148C;line-height:1.6;">
              🔴 <strong>Executive Action Required:</strong> This corrective action has gone unresolved for 15+ days
              despite auditee reminders and plant manager escalation.
              Please take immediate action to ensure compliance.
            </p>
          </div>
          <p style="font-size:15px;color:#333;">Best regards,<br/><strong style="color:#1B5E20;">Quality Team – Northwind</strong></p>
        </div>
        <div style="background:#f8f9fa;padding:15px 30px;text-align:center;border-top:1px solid #e0e0e0;">
          <p style="margin:0;font-size:12px;color:#888;">Automated notification – Northwind Quality Management System</p>
        </div>
      </div>
    </body></html>"""