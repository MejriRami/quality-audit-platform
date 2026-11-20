"""Unit tests for the pure audit-planning rules (no DB / network).

Run from the backend root:  python -m unittest tests.test_audit_planning_rules -v
"""

import unittest
from datetime import date, datetime

from app.services.audit_planning import rules
from app.services.audit_planning.rules import (
    Complaint,
    Escalation,
    Facts,
    HistoryEntry,
    MetricReading,
    Project,
    SupportProcess,
)

PLAN_MONTH = date(2026, 10, 1)   # October plan
AS_OF = date(2026, 10, 1)        # generated on the 1st; lookback = September


def complaint(i, plant="frankfort", line="brush", status="d3", opened=date(2026, 9, 10),
              due=None, closed=None, overdue_step=False, customer=None, defect="Function"):
    return Complaint(
        i, f"C-{i}", plant, line, status, opened, due,
        closed_at=closed, has_overdue_step=overdue_step,
        customer=customer or f"customer-{i}", defect=defect,
    )


def facts(**kw) -> Facts:
    base = dict(
        plan_month=PLAN_MONTH,
        as_of=AS_OF,
        complaints=[],
        projects=[],
        escalations=[],
        metrics=[],
        external_audits={},
        history=[
            # plant-level P7/P9 satisfied everywhere unless a test says otherwise
            HistoryEntry(p, None, k, None, date(2026, 9, 1))
            for p in rules.SCHEDULED_PLANTS
            for k in (rules.HISTORY_PLANT_MANAGER, rules.HISTORY_RECOVERY_PLAN)
        ],
    )
    base.update(kw)
    return Facts(**base)


def by_codes(evaluation):
    return {tuple(c.trigger_codes): c for c in evaluation.candidates}


class ComplaintChecks(unittest.TestCase):
    def p1_refs(self, complaints):
        ev = rules.evaluate(facts(complaints=complaints))
        return sorted(
            e["complaint"] for c in ev.candidates for e in c.evidence if e["check"] == "P1"
        )

    def test_p1_not_closed_on_time(self):
        self.assertEqual(
            self.p1_refs([
                complaint(1, due=datetime(2026, 9, 20)),                   # open, past due
                complaint(2, due=datetime(2026, 10, 20)),                  # open, not yet due
                complaint(3, overdue_step=True),                           # open, 8D step overdue
                complaint(4, status="closed", due=datetime(2026, 9, 1),
                          closed=datetime(2026, 9, 15)),                   # closed late last month
                complaint(5, status="closed", due=datetime(2026, 9, 20),
                          closed=datetime(2026, 9, 15)),                   # closed on time
                complaint(6, status="closed", due=datetime(2026, 7, 1),
                          closed=datetime(2026, 8, 2)),                    # late, but before last month
                complaint(7, status="cancelled", due=datetime(2026, 9, 1)),
            ]),
            ["C-1", "C-3", "C-4"],
        )

    def test_p1_uses_8d_checklist(self):
        (cand,) = rules.evaluate(facts(complaints=[complaint(1, overdue_step=True)])).candidates
        self.assertEqual((cand.trigger_codes, cand.checklist), (["P1"], "Open Audit: Audit the 8D"))

    def test_p4_needs_more_than_three_last_month_excluding_cancelled(self):
        three = [complaint(i) for i in range(3)] + [complaint(9, status="cancelled")]
        self.assertFalse(rules.evaluate(facts(complaints=three)).candidates)
        four = [complaint(i) for i in range(4)]
        (cand,) = rules.evaluate(facts(complaints=four)).candidates
        self.assertEqual(cand.trigger_codes, ["P4"])
        self.assertTrue(cand.checklist.startswith("Open Audit: Process owner for customer complaints"))

    def test_p4_ignores_complaints_outside_last_month(self):
        old = [complaint(i, opened=date(2026, 8, 30)) for i in range(5)]
        self.assertFalse(rules.evaluate(facts(complaints=old)).candidates)

    def test_p5_same_complaint_twice_last_month(self):
        ev = rules.evaluate(facts(complaints=[
            complaint(1, customer="VALEO"),
            complaint(2, customer="valeo "),                          # same customer
            complaint(3, customer="VALEO", defect="Appearance"),      # other defect
        ]))
        (cand,) = ev.candidates
        self.assertEqual(cand.trigger_codes, ["P5"])
        self.assertTrue(cand.checklist.startswith("Open Audit: Previous 8D"))
        self.assertEqual(cand.evidence[0]["complaints"], ["C-1", "C-2"])

    def test_p5_ignores_na_defect_other_months_and_single_complaints(self):
        ev = rules.evaluate(facts(complaints=[
            complaint(1, customer="TRICO", defect="NA"),
            complaint(2, customer="TRICO", defect="NA"),
            complaint(3, customer="MAHLE", opened=date(2026, 8, 20)),
            complaint(4, customer="MAHLE"),
        ]))
        self.assertFalse(ev.candidates)

    def test_p4_and_p5_on_same_line_merge_into_one_audit(self):
        cs = [complaint(i) for i in range(3)] + [
            complaint(5, customer="VALEO"), complaint(6, customer="VALEO")
        ]
        (cand,) = rules.evaluate(facts(complaints=cs)).candidates
        self.assertEqual(cand.trigger_codes, ["P4", "P5"])
        self.assertEqual(cand.checklist.count(" + "), 1)
        self.assertIn("Previous 8D", cand.checklist)

    def test_p4_and_p5_on_different_lines_stay_separate(self):
        cs = [complaint(i) for i in range(4)] + [
            complaint(5, line="choke", customer="VALEO"),
            complaint(6, line="choke", customer="VALEO"),
        ]
        self.assertEqual(set(by_codes(rules.evaluate(facts(complaints=cs)))), {("P4",), ("P5",)})

    def test_source_names_normalize(self):
        self.assertEqual(
            [rules.normalize_plant(p) for p in ("ATLAS/Tunisia", "Korea", "FRANKFURT", "Loire/Amiens")],
            ["atlas", "daegu", "frankfort", "loire"],
        )
        self.assertEqual(
            {rules.normalize_product_line(v) for v in ("BRUSH", "Brushes", "BRU")}, {"brush"}
        )


class OtherChecks(unittest.TestCase):
    def test_p2_p3_merge_per_line(self):
        ev = rules.evaluate(facts(escalations=[
            Escalation(1, "carthage", "chokes", "Bosch", "CSII"),
            Escalation(2, "carthage", "chokes", "Valeo", "CSI"),
        ]))
        (cand,) = ev.candidates
        self.assertEqual(cand.trigger_codes, ["P2", "P3"])
        self.assertEqual(cand.auditee_role, "Quality manager")

    def test_p6_sop_within_five_months(self):
        ev = rules.evaluate(facts(projects=[
            Project("A", "in", "monterrey", "brush", date(2027, 2, 15), "Ana", "user112@example.com"),
            Project("B", "out", "monterrey", "brush", date(2027, 3, 2), "Bo", "user011@example.com"),
        ]))
        (cand,) = ev.candidates
        self.assertEqual(cand.project_code, "A")
        self.assertEqual(cand.auditee_role, "Project manager")

    def test_p7_p9_fire_without_recent_history(self):
        hist = [h for h in facts().history if h.plant != "daegu"]
        hist.append(HistoryEntry("daegu", None, rules.HISTORY_PLANT_MANAGER, None, date(2026, 6, 15)))
        ev = rules.evaluate(facts(history=hist))
        self.assertEqual(
            sorted((c.plant, c.trigger_codes[0]) for c in ev.candidates),
            [("daegu", "P7"), ("daegu", "P9")],
        )

    def test_p8_support_processes_when_iatf_due(self):
        sps = [SupportProcess(1, "Purchasing"), SupportProcess(2, "Maintenance")]
        hist = facts().history + [
            HistoryEntry("tianjin", None, rules.HISTORY_SUPPORT_PROCESS, 1, date(2026, 8, 1))
        ]
        ev = rules.evaluate(facts(
            support_processes=sps,
            history=hist,
            external_audits={
                "tianjin": {"IATF16949": date(2027, 1, 20)},   # within 4 months
                "chennai": {"IATF16949": date(2027, 3, 1)},    # too far
            },
        ))
        self.assertEqual(
            [(c.plant, c.support_process_name) for c in ev.candidates],
            [("tianjin", "Maintenance")],
        )

    def test_p10_iso14001_due(self):
        ev = rules.evaluate(facts(external_audits={"poitiers": {"ISO14001": date(2026, 12, 1)}}))
        (cand,) = ev.candidates
        self.assertEqual(cand.trigger_codes, ["P10"])

    def test_validated_upcoming_date_beats_later_pending_row(self):
        # QA Sept 2026 / ANOM-03: Kunshan ISO 14001 rows 23, 52, 72.
        records = [
            ("validated", date(2026, 11, 16)),
            ("pending_review", date(2027, 2, 4)),
            ("validated", date(2025, 12, 10)),
        ]
        due = rules.pick_next_external_audit(records, date(2026, 9, 1))
        self.assertEqual(due, date(2026, 11, 16))
        ev = rules.evaluate(facts(external_audits={"kunshan": {"ISO14001": due}}))
        self.assertEqual([c.trigger_codes for c in ev.candidates], [["P10"]])

    def test_pending_upcoming_date_used_when_no_validated_one(self):
        records = [("validated", date(2026, 2, 9)), ("pending_review", date(2026, 12, 1))]
        self.assertEqual(
            rules.pick_next_external_audit(records, date(2026, 9, 1)), date(2026, 12, 1)
        )

    def test_only_past_dates_return_latest_for_stale_warning(self):
        records = [("validated", date(2025, 12, 10)), ("pending_review", date(2026, 5, 11))]
        self.assertEqual(
            rules.pick_next_external_audit(records, date(2026, 9, 1)), date(2026, 5, 11)
        )

    def test_past_external_audit_dates_warn_instead_of_trigger(self):
        ev = rules.evaluate(facts(
            support_processes=[SupportProcess(1, "Purchasing")],
            external_audits={"kunshan": {"IATF16949": date(2026, 6, 29)}},
        ))
        self.assertFalse(ev.candidates)
        self.assertIn("kunshan IATF16949 2026-06-29", ev.warnings[0])

    def test_p11_any_metric_over_target(self):
        ev = rules.evaluate(facts(metrics=[
            MetricReading("atlas", "ppm_internal", 2100, 2000, "mcp"),
            MetricReading("atlas", "scrap", 1.0, 2.0, "manual"),
            MetricReading("chennai", "nqc", 5.0, 5.0, "manual"),   # equal = on target
        ]))
        (cand,) = ev.candidates
        self.assertEqual((cand.plant, cand.trigger_codes), ("atlas", ["P11"]))
        self.assertEqual([e["metric"] for e in cand.evidence], ["ppm_internal"])

    def test_all_eleven_checks_reported_and_missing_sources_flagged(self):
        ev = rules.evaluate(facts(
            external_audits=None,
            unavailable_reasons={"certifications": "certifications: not connected"},
        ))
        self.assertEqual(set(ev.check_status), {f"P{i}" for i in range(1, 12)})
        self.assertEqual(ev.check_status["P8"]["status"], "not_evaluated")
        self.assertEqual(ev.check_status["P10"]["reason"], "certifications: not connected")
        self.assertEqual(ev.check_status["P1"]["status"], "evaluated")

    def test_plants_outside_schedule_are_warned_not_planned(self):
        ev = rules.evaluate(facts(complaints=[complaint(i, plant="avoplast") for i in range(5)]))
        self.assertFalse(ev.candidates)
        self.assertIn("avoplast", ev.warnings[0])

    def test_complaint_volume_ranks_lines(self):
        cs = [complaint(i, opened=date(2026, 3, 1)) for i in range(7)] + [
            complaint(99, due=datetime(2026, 9, 1))
        ]
        (cand,) = rules.evaluate(facts(complaints=cs)).candidates
        self.assertEqual(cand.complaint_volume, 8)


class PriorityGuide(unittest.TestCase):
    def test_every_priority_has_guide_and_auditee(self):
        codes = {f"P{i}" for i in range(1, 12)}
        self.assertEqual(set(rules.PRIORITY_GUIDE), codes)
        self.assertEqual(set(rules.AUDITEE_ROLE), codes)

    def test_merged_priorities_share_an_audit_type(self):
        g = rules.PRIORITY_GUIDE
        self.assertEqual(g["P2"]["audit_type"], g["P3"]["audit_type"])
        self.assertEqual(g["P4"]["audit_type"], g["P5"]["audit_type"])

    def test_csi_items_use_the_customer_complaint_checklist(self):
        ev = rules.evaluate(facts(escalations=[Escalation(1, "carthage", "choke", "Bosch", "CSII")]))
        self.assertEqual(ev.candidates[0].checklist, "Customer Complaint: CSII/CSI checklist")


class CapacityAndSchedule(unittest.TestCase):
    def cand(self, plant, volume=0, codes=("P1",), line="brushes"):
        c = rules.Candidate(plant=plant, product_line=line, merge_group="8d", history_kind="line",
                            trigger_codes=list(codes))
        c.complaint_volume = volume
        return c

    def test_recent_line_audit_suppresses(self):
        c = self.cand("frankfort")
        rules.apply_recent_line_audit_rule(
            [c], [HistoryEntry("frankfort", "brushes", "line", None, date(2026, 8, 3))], AS_OF
        )
        self.assertEqual(c.status, rules.STATUS_SUPPRESSED_RECENT)

    def test_weekday_and_one_per_week(self):
        cands = [self.cand("frankfort", line=f"l{i}") for i in range(6)]
        rules.schedule(cands, PLAN_MONTH)
        # October 2026 Tuesdays: 6, 13, 20, 27
        self.assertEqual(
            [c.scheduled_date for c in cands[:4]],
            [date(2026, 10, d) for d in (6, 13, 20, 27)],
        )
        self.assertEqual({c.status for c in cands[4:]}, {rules.STATUS_OVER_CAPACITY})

    def test_kunshan_and_anhui_share_a_weekly_slot(self):
        k, a = self.cand("kunshan"), self.cand("anhui")
        rules.schedule([k, a], PLAN_MONTH)
        self.assertEqual({k.scheduled_date, a.scheduled_date}, {date(2026, 10, 5), date(2026, 10, 12)})

    def test_top_offenders_first(self):
        low, high = self.cand("chennai", volume=1, line="a"), self.cand("chennai", volume=9, line="b")
        rules.schedule([low, high], PLAN_MONTH)
        self.assertLess(high.scheduled_date, low.scheduled_date)

    def test_priority_beats_complaint_volume(self):
        p5 = self.cand("chennai", volume=9, codes=("P5",), line="a")
        p1 = self.cand("chennai", volume=1, codes=("P1",), line="b")
        rules.schedule([p5, p1], PLAN_MONTH)
        self.assertLess(p1.scheduled_date, p5.scheduled_date)

    def test_lower_priority_never_dated_before_higher_across_plants(self):
        # Poitiers is Thursday, Kunshan is Monday: without the priority floor
        # the Kunshan P5 would land on Monday 5th, ahead of the P1 on the 8th.
        p1 = self.cand("poitiers", codes=("P1",))
        p5 = self.cand("kunshan", codes=("P5",))
        rules.schedule([p5, p1], PLAN_MONTH, not_before=date(2026, 10, 2))
        self.assertEqual(p1.scheduled_date, date(2026, 10, 8))
        self.assertEqual(p5.scheduled_date, date(2026, 10, 12))

    def test_same_day_allowed_for_lower_priority(self):
        p1 = self.cand("frankfort", codes=("P1",))
        p2 = self.cand("monterrey", codes=("P2",))
        rules.schedule([p2, p1], PLAN_MONTH)
        self.assertEqual(p1.scheduled_date, p2.scheduled_date)   # both Tuesday 6th

    def test_holidays_and_not_before(self):
        c1, c2 = self.cand("carthage"), self.cand("loire")
        rules.schedule(
            [c1, c2],
            PLAN_MONTH,
            holidays={"carthage": {date(2026, 10, 14)}},
            not_before=date(2026, 10, 8),
        )
        self.assertEqual(c1.scheduled_date, date(2026, 10, 21))   # 14th is a holiday
        self.assertEqual(c2.scheduled_date, date(2026, 10, 14))

    def test_suppressed_items_are_not_scheduled(self):
        c = self.cand("daegu")
        c.status = rules.STATUS_SUPPRESSED_RECENT
        rules.schedule([c], PLAN_MONTH)
        self.assertIsNone(c.scheduled_date)

    def test_add_months_clamps_day(self):
        self.assertEqual(rules.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(rules.add_months(date(2026, 3, 15), -3), date(2025, 12, 15))


if __name__ == "__main__":
    unittest.main()
