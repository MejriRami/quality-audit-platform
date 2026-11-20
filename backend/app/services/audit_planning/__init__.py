"""Monthly audit-planning engine (v1).

- rules.py      pure P1-P11 evaluation + capacity scheduling (no I/O, unit-tested)
- sources.py    reads the complaints / projects DBs, the roles MCP and manual inputs
- auditees.py   resolves the responsible person for each plan item
- service.py    orchestrates a run and persists it (audit_plan_* tables)
"""
