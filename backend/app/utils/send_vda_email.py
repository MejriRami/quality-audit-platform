from typing import Any, Dict, List, Optional


def build_vda_result_email_body(
    supplier_name: str,
    audit_reference: str,
    audit_date: str,
    location: str,
    eg_percent: float,
    final_rating: str,
    achieved_points: int,
    max_points: int,
    strong_points: Optional[str] = None,
    weak_points: Optional[str] = None,
    elements: Optional[List[Dict[str, Any]]] = None,
    downgrade_reasons: Optional[List[Dict[str, Any]]] = None,
) -> str:
    strong_points = strong_points or "No specific strengths provided."
    weak_points = weak_points or "No specific improvement opportunities provided."
    elements = elements or []
    downgrade_reasons = downgrade_reasons or []

    rating_color = {
        "A": "#2E7D32",
        "B": "#F9A825",
        "C": "#C62828",
    }.get(final_rating, "#1565C0")

    elements_rows = ""
    for e in elements:
        eg = "n.e." if e["eg_percent"] is None else f'{e["eg_percent"]}%'
        elements_rows += f"""
        <tr>
            <td style="padding:10px;border:1px solid #ddd;">{e['element']}</td>
            <td style="padding:10px;border:1px solid #ddd;">{eg}</td>
            <td style="padding:10px;border:1px solid #ddd;">{e['achieved_points']}/{e['max_points'] or '--'}</td>
        </tr>
        """

    downgrade_html = ""
    if downgrade_reasons:
        items = ""
        for r in downgrade_reasons:
            if r["type"] == "ASTERISK_0":
                items += f"<li>Critical question <b>{r['question_code']}</b> scored <b>0</b> → final rating forced to <b>C</b>.</li>"
            elif r["type"] == "ASTERISK_4":
                items += f"<li>Critical question <b>{r['question_code']}</b> scored <b>4</b> → final rating cannot be <b>A</b>.</li>"
        downgrade_html = f"""
        <h3 style="color:#0D47A1;">Downgrade Reasons</h3>
        <ul style="color:#333;">{items}</ul>
        """
    else:
        downgrade_html = """
        <h3 style="color:#0D47A1;">Downgrade Reasons</h3>
        <p style="color:#333;">No downgrade rules were triggered.</p>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    </head>
    <body style="font-family:Arial,sans-serif;background:#f4f6f8;padding:20px;margin:0;">
      <div style="max-width:900px;margin:auto;background:white;padding:30px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">

        <div style="text-align:center;margin-bottom:20px;">
          <h2 style="margin:0;color:#0D47A1;">Audit report VDA 6.3 – Evaluation of quality capability</h2>
          <p style="margin-top:8px;color:#666;">Reference: <b>{audit_reference}</b></p>
        </div>

        <table style="border-collapse:collapse;width:100%;margin-bottom:20px;">
          <tr>
            <td style="padding:10px;border:1px solid #ddd;"><b>Supplier</b></td>
            <td style="padding:10px;border:1px solid #ddd;">{supplier_name}</td>
          </tr>
          <tr>
            <td style="padding:10px;border:1px solid #ddd;"><b>Date</b></td>
            <td style="padding:10px;border:1px solid #ddd;">{audit_date}</td>
          </tr>
          <tr>
            <td style="padding:10px;border:1px solid #ddd;"><b>Location</b></td>
            <td style="padding:10px;border:1px solid #ddd;">{location}</td>
          </tr>
        </table>

        <div style="background:#f8f9fa;padding:20px;border-radius:8px;margin-bottom:24px;">
          <h3 style="margin-top:0;color:#0D47A1;">Audit Result</h3>
          <p style="font-size:18px;margin:8px 0;"><b>EG:</b> {eg_percent}%</p>
          <p style="font-size:18px;margin:8px 0;">
            <b>Rating:</b>
            <span style="display:inline-block;background:{rating_color};color:white;padding:4px 10px;border-radius:6px;font-weight:700;">
              {final_rating}
            </span>
          </p>
          <p style="margin:8px 0;color:#555;"><b>Points:</b> {achieved_points}/{max_points}</p>
        </div>

        <h3 style="color:#0D47A1;">Compliance by Element</h3>
        <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
          <thead>
            <tr style="background:#eeeeee;">
              <th style="padding:10px;border:1px solid #ddd;text-align:left;">Element</th>
              <th style="padding:10px;border:1px solid #ddd;text-align:left;">EG [%]</th>
              <th style="padding:10px;border:1px solid #ddd;text-align:left;">Points</th>
            </tr>
          </thead>
          <tbody>
            {elements_rows}
          </tbody>
        </table>

        {downgrade_html}

        <h3 style="color:#0D47A1;">Strengths</h3>
        <p style="color:#333;white-space:pre-line;">{strong_points}</p>

        <h3 style="color:#0D47A1;">Opportunities for Improvement</h3>
        <p style="color:#333;white-space:pre-line;">{weak_points}</p>

        <hr style="margin:24px 0;" />
        <p style="font-size:12px;color:#666;">
          Classification scale: A = 90–100%, B = 80–89%, C &lt; 80%
        </p>

        <p style="margin-top:20px;">
          Best regards,<br/>
          <strong>Quality Team – Northwind</strong>
        </p>
      </div>
    </body>
    </html>
    """