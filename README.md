# Quality Audit Platform

**▶ [Video walkthrough (6 min)](https://mejrirami.github.io/demos/#audit)**

A full-stack platform for manufacturing quality audits: internal audits, VDA 6.3, IATF 16949 and ISO 14001,
from planning to closed corrective actions, with two AI assistants built in.

## Features

- **KPI dashboard**: audits planned / completed / postponed, open and overdue corrective actions (CARs), average score, by plant and period.
- **Audit planning and execution**: checklists per standard (VDA 6.3 with potential analysis P1 and 0/4/6/8/10 scoring, IATF 16949, ISO 14001, internal), continuous draft saving, evidence upload, PDF report on closing, Outlook calendar sync.
- **Automatic monthly planning**: a pure rule engine (`backend/app/services/audit_planning/rules.py`) combines customer complaints and their 8D status, APQP projects close to SOP, external certification dates and KPIs, applies 11 priority rules (P1–P11), explains *why* each audit is proposed, and schedules them into each plant's weekly slots. The quality manager reviews, adjusts and approves.
- **Corrective actions**: every finding becomes a CAR with due dates, reminders and multi-level escalation; auditors accept or reject submissions.
- **Auditee portal**: account-less access with an email one-time code, scoped to the auditee's own audits and CARs.
- **AI CAR coach** (`backend/app/services/chatbot_service.py`): guides the auditee through containment and a 5-Whys root-cause analysis question by question (it never writes the answer for them), then drafts the 5 Whys and the implemented solution **only from the auditee's own words**, for review before submission.
- **AI auditor assistant** (`backend/app/services/auditor_chatbot_service.py`): answers from the audits, findings and CARs in the signed-in user's scope, and coaches on audit method (e.g. writing a VDA 6.3 finding).
- **Questionnaire library** with versioning and an approval workflow; **external certifications** with documents, nonconformities and expiry alerts; **multi-audit consolidation** into one themed report; role-based admin console; plant holidays.

## Architecture

| Part | Stack |
|---|---|
| `backend/` | Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, APScheduler (reminders, escalations, monthly plan), OpenAI API, Microsoft Graph (mail, calendar), Azure Blob Storage |
| `frontend/` | React, TypeScript, Vite, Tailwind CSS, Redux Toolkit |

The planning engine reads three other systems (complaints/8D, APQP projects, certifications) through read-only connections; each source can be pointed elsewhere with its own `*_DATABASE_URL`.

## Run locally

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                 # fill in DATABASE_URL, JWT_SECRET_KEY, OPENAI_API_KEY ...
alembic upgrade head
uvicorn app.main:app --port 8000

# frontend
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npx vite
```

Company, people and site names in this repository are fictional (the company is "Northwind").
