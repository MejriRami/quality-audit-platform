import { useEffect, useState } from "react";
import { toast } from "react-hot-toast";
import {
  AuditorHoliday,
  createAuditorHoliday,
  deleteAuditorHoliday,
  fetchAuditorHolidays,
} from "../../services/correctiveActionsApi";

const todayIso = () => new Date().toISOString().slice(0, 10);

export default function AuditorHolidayWidget() {
  const [holidays, setHolidays] = useState<AuditorHoliday[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [startDate, setStartDate] = useState(todayIso());
  const [endDate, setEndDate] = useState(todayIso());
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);

  const load = () => {
    fetchAuditorHolidays()
      .then(setHolidays)
      .catch(() => {
        /* silently ignore — non-critical widget */
      });
  };

  useEffect(() => {
    load();
  }, []);

  const today = todayIso();
  const activeOrUpcoming = holidays.filter((h) => h.end_date >= today);

  const submit = async () => {
    if (!startDate || !endDate || endDate < startDate) {
      toast.error("End date must be on or after start date.");
      return;
    }
    try {
      setLoading(true);
      await createAuditorHoliday({
        start_date: startDate,
        end_date: endDate,
        reason: reason || undefined,
      });
      toast.success("Holiday period saved — CAR escalation will pause for your audits.");
      setShowForm(false);
      setReason("");
      load();
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to save holiday period.";
      toast.error(detail);
    } finally {
      setLoading(false);
    }
  };

  const remove = async (id: number) => {
    try {
      await deleteAuditorHoliday(id);
      setHolidays((prev) => prev.filter((h) => h.id !== id));
    } catch {
      toast.error("Failed to remove holiday period.");
    }
  };

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 dark:border-indigo-900 dark:bg-indigo-950/20 px-4 py-3 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-indigo-900 dark:text-indigo-200">
            On Holiday
          </h3>
          <p className="text-xs text-indigo-700 dark:text-indigo-300">
            Pause CAR escalation for your audits while you're away.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="text-xs font-medium px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
        >
          {showForm ? "Cancel" : "I'm going on holiday"}
        </button>
      </div>

      {activeOrUpcoming.length > 0 && (
        <ul className="space-y-1">
          {activeOrUpcoming.map((h) => (
            <li
              key={h.id}
              className="flex items-center justify-between gap-2 text-xs text-indigo-900 dark:text-indigo-200 bg-white/70 dark:bg-white/5 rounded-lg px-3 py-1.5"
            >
              <span>
                {h.start_date} → {h.end_date}
                {h.reason ? ` — ${h.reason}` : ""}
              </span>
              <button
                onClick={() => remove(h.id)}
                className="text-indigo-400 hover:text-red-600 transition-colors"
                title="Remove"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      {showForm && (
        <div className="flex flex-wrap items-end gap-2 pt-1">
          <div>
            <label className="block text-[11px] text-indigo-700 dark:text-indigo-300 mb-1">
              Start date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="text-sm border border-indigo-300 rounded-lg px-2 py-1.5 bg-white"
            />
          </div>
          <div>
            <label className="block text-[11px] text-indigo-700 dark:text-indigo-300 mb-1">
              End date
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="text-sm border border-indigo-300 rounded-lg px-2 py-1.5 bg-white"
            />
          </div>
          <div className="flex-1 min-w-[160px]">
            <label className="block text-[11px] text-indigo-700 dark:text-indigo-300 mb-1">
              Reason (optional)
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Vacation"
              className="w-full text-sm border border-indigo-300 rounded-lg px-2 py-1.5 bg-white"
            />
          </div>
          <button
            onClick={submit}
            disabled={loading}
            className="text-xs font-medium px-3 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-gray-300 transition-colors"
          >
            {loading ? "Saving..." : "Save"}
          </button>
        </div>
      )}
    </div>
  );
}
