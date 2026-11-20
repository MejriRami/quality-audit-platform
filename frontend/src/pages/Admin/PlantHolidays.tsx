import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import { CalendarDays, MapPinned, PlusCircle, Trash2 } from "lucide-react";
import {
  PlantHolidayItem,
  adminAddPlantHoliday,
  adminDeletePlantHoliday,
  adminListPlantHolidays,
} from "../../services/adminApi";

const emptyForm = {
  plant: "",
  holiday_date: "",
  name: "",
};

export default function PlantHolidays() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [plants, setPlants] = useState<string[]>([]);
  const [holidays, setHolidays] = useState<PlantHolidayItem[]>([]);
  const [selectedPlant, setSelectedPlant] = useState("");
  const [form, setForm] = useState(emptyForm);

  const loadHolidays = async (plant?: string) => {
    setLoading(true);
    try {
      const data = await adminListPlantHolidays(plant || undefined);
      setPlants(data.system_plants);
      setHolidays(data.items);
    } catch (err: any) {
      toast.error(
        err?.response?.data?.detail || "Failed to load plant holidays",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadHolidays();
  }, []);

  const groupedHolidays = useMemo(() => {
    return holidays.reduce<Record<string, PlantHolidayItem[]>>(
      (acc, holiday) => {
        const key = holiday.plant || "Unknown";
        acc[key] = acc[key] || [];
        acc[key].push(holiday);
        return acc;
      },
      {},
    );
  }, [holidays]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await adminAddPlantHoliday(form);
      toast.success("Plant holiday added");
      setForm(emptyForm);
      await loadHolidays(selectedPlant);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to save holiday");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (holiday: PlantHolidayItem) => {
    try {
      await adminDeletePlantHoliday(holiday.id);
      toast.success("Holiday removed");
      await loadHolidays(selectedPlant);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to delete holiday");
    }
  };

  return (
    <div className="space-y-6">
      <PageMeta
        title="Plant Holidays"
        description="Maintain plant calendars for accurate audit scheduling."
      />
      <PageBreadcrumb
        kicker="Administration"
        pageTitle="Plant Holiday Management"
        description="Keep local plant calendars current so audit planning reflects working days across sites."
        actions={
          <>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200/70 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm dark:border-slate-800/70 dark:bg-slate-950/60 dark:text-slate-100">
              <MapPinned className="h-3.5 w-3.5" />
              {plants.length} plants
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200/70 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm dark:border-slate-800/70 dark:bg-slate-950/60 dark:text-slate-100">
              <CalendarDays className="h-3.5 w-3.5" />
              {holidays.length} holidays
            </span>
          </>
        }
      />

      <section className="grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="rounded-2xl border border-slate-200/70 bg-white p-5 shadow-sm dark:border-slate-800/70 dark:bg-slate-900/60">
          <div className="flex items-center gap-2">
            <PlusCircle className="h-5 w-5 text-slate-600 dark:text-slate-200" />
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              Add Plant Holiday
            </h2>
          </div>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Add official closure dates that should pause working-day
            calculations.
          </p>

          <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
            <select
              className="w-full rounded-xl border border-[#9ec6df] px-3 py-2.5 text-sm dark:border-[#0f6ea9] dark:bg-[#09304b] dark:text-white"
              value={form.plant}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, plant: e.target.value }))
              }
              required
            >
              <option value="">Select plant</option>
              {plants.map((plant) => (
                <option key={plant} value={plant}>
                  {plant}
                </option>
              ))}
            </select>

            <input
              type="date"
              className="w-full rounded-xl border border-[#9ec6df] px-3 py-2.5 text-sm dark:border-[#0f6ea9] dark:bg-[#09304b] dark:text-white"
              value={form.holiday_date}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, holiday_date: e.target.value }))
              }
              required
            />

            <input
              className="w-full rounded-xl border border-[#9ec6df] px-3 py-2.5 text-sm dark:border-[#0f6ea9] dark:bg-[#09304b] dark:text-white"
              placeholder="Holiday name"
              value={form.name}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, name: e.target.value }))
              }
            />

            <button
              type="submit"
              disabled={saving}
              className="w-full rounded-xl bg-gradient-to-r from-[#064273] to-[#0a5f95] px-4 py-2.5 text-sm font-semibold text-white transition hover:from-[#05375f] hover:to-[#084d79] disabled:opacity-60"
            >
              {saving ? "Saving..." : "Save Holiday"}
            </button>
          </form>
        </div>

        <div className="rounded-2xl border border-[#b8d3e6] bg-white/95 p-5 shadow-sm dark:border-[#0a5f95] dark:bg-[#072f4a]/80">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-[#064273] dark:text-[#e1f2ff]">
                Existing Holidays
              </h2>
              <p className="mt-1 text-sm text-[#4b738e] dark:text-[#b8dcf2]">
                Review configured closures by plant and keep site calendars
                accurate.
              </p>
            </div>
            <select
              className="rounded-xl border border-[#9ec6df] px-3 py-2 text-sm dark:border-[#0f6ea9] dark:bg-[#09304b] dark:text-white"
              value={selectedPlant}
              onChange={(e) => {
                const nextPlant = e.target.value;
                setSelectedPlant(nextPlant);
                void loadHolidays(nextPlant);
              }}
            >
              <option value="">All plants</option>
              {plants.map((plant) => (
                <option key={plant} value={plant}>
                  {plant}
                </option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="mt-5 rounded-2xl border border-dashed border-[#c7dceb] px-4 py-12 text-center text-sm text-[#5e8198] dark:border-[#215777] dark:text-[#b8dcf2]">
              Loading plant holidays...
            </div>
          ) : holidays.length === 0 ? (
            <div className="mt-5 rounded-2xl border border-dashed border-[#c7dceb] px-4 py-12 text-center text-sm text-[#5e8198] dark:border-[#215777] dark:text-[#b8dcf2]">
              No plant holidays configured yet.
            </div>
          ) : (
            <div className="mt-5 space-y-5">
              {Object.entries(groupedHolidays).map(([plant, items]) => (
                <div
                  key={plant}
                  className="rounded-2xl border border-[#dbe8f1] dark:border-[#14486a]"
                >
                  <div className="flex items-center justify-between gap-3 border-b border-[#dbe8f1] bg-[#f6fbff] px-4 py-3 dark:border-[#14486a] dark:bg-[#08304c]">
                    <div>
                      <p className="text-sm font-semibold text-[#0d3550] dark:text-[#e1f2ff]">
                        {plant}
                      </p>
                      <p className="text-xs text-[#5d7e94] dark:text-[#a9cee5]">
                        {items.length} configured date
                        {items.length === 1 ? "" : "s"}
                      </p>
                    </div>
                  </div>
                  <div className="divide-y divide-[#edf4f8] dark:divide-[#123f5f]">
                    {items.map((holiday) => (
                      <div
                        key={holiday.id}
                        className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
                      >
                        <div>
                          <p className="text-sm font-medium text-[#0d3550] dark:text-[#eaf6ff]">
                            {holiday.name || "Plant holiday"}
                          </p>
                          <p className="text-xs text-[#5d7e94] dark:text-[#a9cee5]">
                            {holiday.holiday_date}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => void handleDelete(holiday)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 transition hover:bg-rose-100 dark:border-rose-900/40 dark:bg-rose-900/20 dark:text-rose-300"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
