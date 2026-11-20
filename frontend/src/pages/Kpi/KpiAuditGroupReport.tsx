import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";

import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import ComponentCard from "../../components/common/ComponentCard";
import Select from "../../components/form/Select";

/** ---------------------------
 * Types (same style as your old page)
 * -------------------------- */
type ReferenceLine = { value: number; label?: string };

type KpiStackedResponse = {
  groupBy: string;
  stackBy: string;
  unit?: "hours" | "count";
  keys: string[];
  data: Array<{ group: string; [k: string]: number | string }>;
  referenceLines?: ReferenceLine[];
};

type KpiCountScoreResponse = {
  groupBy: string;
  unitLeft: "count";
  unitRight: "score";
  data: Array<{ group: string; count: number; score: number }>;
  gradeLines: Array<{ value: number; label: string }>;
};

type KpiSimpleSeriesResponse = {
  groupBy: string;
  unit: "days" | "count";
  data: Array<{ group: string; value: number }>;
  referenceLines?: ReferenceLine[];
};

const API_BASE = import.meta.env.VITE_API_URL as string | undefined;

async function fetchJson<T>(path: string): Promise<T> {
  if (!API_BASE) throw new Error("VITE_API_URL is not set (.env).");

  const res = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  const text = await res.text();

  if (!res.ok)
    throw new Error(`Request failed ${res.status}: ${text.slice(0, 200)}...`);

  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(
      `Expected JSON from ${API_BASE}${path} but got:\n${text.slice(0, 200)}...`
    );
  }
}

/** ---------------------------
 * Helpers
 * -------------------------- */
const toTitle = (s: string) =>
  s ? s.charAt(0).toUpperCase() + s.slice(1) : s;

function num(v: any) {
  const x = Number(v);
  return Number.isFinite(x) ? x : 0;
}

function avg(nums: number[]) {
  if (!nums.length) return undefined;
  return nums.reduce((s, x) => s + x, 0) / nums.length;
}

function lastN<T>(arr: T[], n: number) {
  return arr.slice(Math.max(0, arr.length - n));
}

/** ---------------------------
 * Plant colors (stable)
 * -------------------------- */
const PLANT_COLORS: Record<string, string> = {
  atlas: "#0062ff",
  carthage: "#1bb1d3",
  medina: "#f65ce7",
  monterrey: "#9e6e1b",
  tianjin: "#000000",
  kunshan: "#ef2c2c",
  chennai: "#4b024b",
  frankfort: "#F97316",
  rayones: "#A3A3A3",
  daegu: "#0EA5E9",
  anhui: "#14B8A6",
  galeana: "#cc1616",
  poitiers: "#fb7171",
  loire: "#519391a8",
};

/** ---------------------------
 * Responsive observer
 * -------------------------- */
function useResizeObserver(targetRef: React.RefObject<HTMLElement | SVGElement>) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const el = targetRef.current as any;
    if (!el) return;

    const ro = new ResizeObserver(() => setTick((t) => t + 1));
    const node: Element =
      el instanceof SVGElement ? (el.parentElement ?? el) : el;

    ro.observe(node);
    return () => ro.disconnect();
  }, [targetRef]);

  return tick;
}

/** ---------------------------
 * Chart 1: Combo bars (count) + line (score) + optional target line
 * (close to your ComboBarLineD3 but with an optional targetScore line)
 * -------------------------- */
function ComboAuditCountScoreD3({
  data,
  height = 320,
  targetScore, // optional fixed target score (0..100)
}: {
  data: Array<{ group: string; count: number; score: number }>;
  height?: number;
  targetScore?: number;
}) {
  const ref = useRef<SVGSVGElement | null>(null);
  const resizeTick = useResizeObserver(ref as any);

  useEffect(() => {
    if (!ref.current) return;
    if (!data?.length) return;

    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();

    const width = ref.current.parentElement?.clientWidth ?? 900;
    const margin = { top: 18, right: 56, bottom: 44, left: 60 };

    svg
      .attr("width", width)
      .attr("height", height)
      .attr("viewBox", `0 0 ${width} ${height}`)
      .style("max-width", "100%")
      .style("height", "auto");

    const x = d3
      .scaleBand<string>()
      .domain(data.map((d) => d.group))
      .range([margin.left, width - margin.right])
      .padding(0.25);

    const yLeft = d3
      .scaleLinear()
      .domain([0, d3.max(data, (d) => d.count) ?? 0])
      .nice()
      .range([height - margin.bottom, margin.top]);

    const yRight = d3
      .scaleLinear()
      .domain([0, 100])
      .range([height - margin.bottom, margin.top]);

    // Target score line if provided
    if (typeof targetScore === "number") {
      svg
        .append("line")
        .attr("x1", margin.left)
        .attr("x2", width - margin.right)
        .attr("y1", yRight(targetScore))
        .attr("y2", yRight(targetScore))
        .attr("stroke", "#22C55E")
        .attr("stroke-dasharray", "6 4")
        .attr("stroke-width", 1.2);

      svg
        .append("text")
        .attr("x", width - margin.right)
        .attr("y", yRight(targetScore) - 6)
        .attr("text-anchor", "end")
        .style("font-size", "12px")
        .style("fill", "#22C55E")
        .text(`Target (${targetScore})`);
    }

    // Bars (count)
    svg
      .append("g")
      .selectAll("rect")
      .data(data)
      .join("rect")
      .attr("x", (d) => x(d.group)!)
      .attr("y", (d) => yLeft(d.count))
      .attr("width", x.bandwidth())
      .attr("height", (d) => yLeft(0) - yLeft(d.count))
      .attr("fill", "#0B3D91")
      .append("title")
      .text((d) => `Audits: ${d.count}`);

    // Line (score)
    const line = d3
      .line<{ group: string; count: number; score: number }>()
      .x((d) => x(d.group)! + x.bandwidth() / 2)
      .y((d) => yRight(d.score));

    svg
      .append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", "#F97316")
      .attr("stroke-width", 2)
      .attr("d", line);

    svg
      .append("g")
      .selectAll("circle")
      .data(data)
      .join("circle")
      .attr("cx", (d) => x(d.group)! + x.bandwidth() / 2)
      .attr("cy", (d) => yRight(d.score))
      .attr("r", 3)
      .attr("fill", "#F97316")
      .append("title")
      .text((d) => `Score: ${d.score.toFixed(1)}`);

    // Axes
    svg
      .append("g")
      .attr("transform", `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).tickSizeOuter(0));

    svg
      .append("g")
      .attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(yLeft).ticks(6));

    svg
      .append("g")
      .attr("transform", `translate(${width - margin.right},0)`)
      .call(d3.axisRight(yRight).ticks(5));
  }, [data, height, targetScore, resizeTick]);

  return <svg ref={ref} />;
}

/** ---------------------------
 * Chart 2: two bars (CAR created + Late CAR) + line (closing days) right axis
 * -------------------------- */
function MultiBarLineD3({
  data,
  height = 320,
  leftMaxPad = 1.15,
}: {
  data: Array<{
    group: string;
    createdCar: number;
    lateCar: number;
    closingDays: number;
  }>;
  height?: number;
  leftMaxPad?: number;
}) {
  const ref = useRef<SVGSVGElement | null>(null);
  const resizeTick = useResizeObserver(ref as any);

  useEffect(() => {
    if (!ref.current) return;
    if (!data?.length) return;

    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();

    const width = ref.current.parentElement?.clientWidth ?? 900;
    const margin = { top: 18, right: 56, bottom: 44, left: 60 };

    svg
      .attr("width", width)
      .attr("height", height)
      .attr("viewBox", `0 0 ${width} ${height}`)
      .style("max-width", "100%")
      .style("height", "auto");

    const x = d3
      .scaleBand<string>()
      .domain(data.map((d) => d.group))
      .range([margin.left, width - margin.right])
      .padding(0.25);

    const yLeftMax =
      (d3.max(data, (d) => Math.max(d.createdCar, d.lateCar)) ?? 0) * leftMaxPad;

    const yLeft = d3
      .scaleLinear()
      .domain([0, yLeftMax])
      .nice()
      .range([height - margin.bottom, margin.top]);

    const yRight = d3
      .scaleLinear()
      .domain([0, d3.max(data, (d) => d.closingDays) ?? 0])
      .nice()
      .range([height - margin.bottom, margin.top]);

    // two bars inside band
    const inner = d3
      .scaleBand<string>()
      .domain(["created", "late"])
      .range([0, x.bandwidth()])
      .padding(0.18);

    // created CAR bars
    svg
      .append("g")
      .selectAll("rect.created")
      .data(data)
      .join("rect")
      .attr("class", "created")
      .attr("x", (d) => x(d.group)! + inner("created")!)
      .attr("y", (d) => yLeft(d.createdCar))
      .attr("width", inner.bandwidth())
      .attr("height", (d) => yLeft(0) - yLeft(d.createdCar))
      .attr("fill", "#0B3D91")
      .append("title")
      .text((d) => `CAR created: ${d.createdCar}`);

    // late CAR bars
    svg
      .append("g")
      .selectAll("rect.late")
      .data(data)
      .join("rect")
      .attr("class", "late")
      .attr("x", (d) => x(d.group)! + inner("late")!)
      .attr("y", (d) => yLeft(d.lateCar))
      .attr("width", inner.bandwidth())
      .attr("height", (d) => yLeft(0) - yLeft(d.lateCar))
      .attr("fill", "#F97316")
      .append("title")
      .text((d) => `Late CAR: ${d.lateCar}`);

    // closing days line
    const line = d3
      .line<{ group: string; createdCar: number; lateCar: number; closingDays: number }>()
      .x((d) => x(d.group)! + x.bandwidth() / 2)
      .y((d) => yRight(d.closingDays));

    svg
      .append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", "#60A5FA")
      .attr("stroke-width", 2)
      .attr("d", line);

    svg
      .append("g")
      .selectAll("circle")
      .data(data)
      .join("circle")
      .attr("cx", (d) => x(d.group)! + x.bandwidth() / 2)
      .attr("cy", (d) => yRight(d.closingDays))
      .attr("r", 3)
      .attr("fill", "#60A5FA")
      .append("title")
      .text((d) => `Closing days: ${d.closingDays.toFixed(1)}`);

    // Axes
    svg
      .append("g")
      .attr("transform", `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).tickSizeOuter(0));

    svg
      .append("g")
      .attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(yLeft).ticks(6));

    svg
      .append("g")
      .attr("transform", `translate(${width - margin.right},0)`)
      .call(d3.axisRight(yRight).ticks(5));
  }, [data, height, leftMaxPad, resizeTick]);

  return <svg ref={ref} />;
}

/** ---------------------------
 * KPI side panel (right column)
 * -------------------------- */
function KpiSidePanel({
  auditScore12w,
  auditScoreLast,
  auditScoreDelta,
  lastWeekLabel,
  closingDays12w,
  closingDaysLast,
  closingDaysDelta,
}: {
  auditScore12w?: number;
  auditScoreLast?: number;
  auditScoreDelta?: number;
  lastWeekLabel?: string;
  closingDays12w?: number;
  closingDaysLast?: number;
  closingDaysDelta?: number;
}) {
  const arrow = (delta?: number) => {
    if (delta == null) return null;
    if (delta > 0) return <span className="text-green-600">↗</span>;
    if (delta < 0) return <span className="text-red-600">↘</span>;
    return <span className="text-gray-500">→</span>;
  };

  const fmt = (v?: number, digits = 1) => (v == null ? "-" : v.toFixed(digits));

  return (
    <div className="h-full flex flex-col justify-center gap-4 px-2">
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500">12 Week Audit Score</div>
        <div className="text-lg font-semibold">{fmt(auditScore12w, 0)}</div>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500">Last Audits Score</div>
        <div className="flex items-center gap-2">
          <div className="text-lg font-semibold">{fmt(auditScoreLast, 0)}</div>
          {arrow(auditScoreDelta)}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500">Last Week Audits</div>
        <div className="text-lg font-semibold">{lastWeekLabel ?? "-"}</div>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500">12 Weeks CAR Closing Days</div>
        <div className="text-lg font-semibold">{fmt(closingDays12w, 1)}</div>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-500">Last Week CAR Closing Days</div>
        <div className="flex items-center gap-2">
          <div className="text-lg font-semibold">{fmt(closingDaysLast, 1)}</div>
          {arrow(closingDaysDelta)}
        </div>
      </div>
    </div>
  );
}

/** ---------------------------
 * Main page (single file, everything here)
 * -------------------------- */
export default function KpiAuditGroupReportPage() {
  const [from, setFrom] = useState("2025-01-01");
  const [to, setTo] = useState("2026-01-31");
  const [auditTypeId, setAuditTypeId] = useState("all");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Data by plant
  const [dataByPlant, setDataByPlant] = useState<
    Array<{
      plant: string;
      auditCountScore: KpiCountScoreResponse | null;
      carCreatedWeekly: KpiStackedResponse | null;
      lateCarWeekly: KpiStackedResponse | null;
      closingDaysWeekly: KpiSimpleSeriesResponse | null;
    }>
  >([]);

  const plants = useMemo(
    () => [
      "atlas",
      "carthage",
      "medina",
      "monterrey",
      "tianjin",
      "kunshan",
      "chennai",
      "frankfort",
      "rayones",
      "daegu",
      "anhui",
      "galeana",
      "poitiers",
      "loire",
    ],
    []
  );

  const typeOptions = useMemo(
    () => [
      { value: "all", label: "All types" },
      // later: populate from GET /audit-types/
    ],
    []
  );

  const qsBase = useMemo(() => {
    const p = new URLSearchParams();
    p.set("from", from);
    p.set("to", to);
    if (auditTypeId !== "all") p.set("audit_type_id", auditTypeId);
    return p.toString();
  }, [from, to, auditTypeId]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const all = await Promise.all(
          plants.map(async (plant) => {
            const qsPlant = `${qsBase}&plant=${encodeURIComponent(plant)}`;

            const [auditCountScore, carCreatedWeekly, lateCarWeekly, closingDaysWeekly] =
              await Promise.all([
                fetchJson<KpiCountScoreResponse>(
                  `/kpi/audit-count-score?interval=week&date_basis=planned&${qsPlant}`
                ),
                fetchJson<KpiStackedResponse>(`/kpi/car-count?interval=week&${qsPlant}`),
                fetchJson<KpiStackedResponse>(`/kpi/late-car?interval=week&${qsPlant}`),
                fetchJson<KpiSimpleSeriesResponse>(
                  `/kpi/avg-days-close-car?interval=week&${qsPlant}`
                ),
              ]);

            return {
              plant,
              auditCountScore,
              carCreatedWeekly,
              lateCarWeekly,
              closingDaysWeekly,
            };
          })
        );

        setDataByPlant(all);
      } catch (e: any) {
        setError(e?.message ?? "Failed to load report");
      } finally {
        setLoading(false);
      }
    })();
  }, [plants, qsBase]);

  // extract plant series from stacked response (keys/data)
  const stackedToSingle = (resp: KpiStackedResponse | null, plant: string) => {
    if (!resp) return [];
    const key = resp.keys.find((k) => k === plant);
    if (!key) return [];
    return resp.data.map((row) => ({
      group: String(row.group),
      value: num((row as any)[key]),
    }));
  };

  const simpleToSeries = (resp: KpiSimpleSeriesResponse | null) => {
    if (!resp) return [];
    return resp.data.map((d) => ({ group: String(d.group), value: num(d.value) }));
  };

  return (
    <div className="p-6 space-y-6">
      <PageMeta title="Remote Audit Group Report" description="Weekly per-plant report" />
      <PageBreadcrumb pageTitle="Remote Audit Group Report" />

      <ComponentCard title="Filters">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase mb-2">From</p>
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800"
            />
          </div>

          <div>
            <p className="text-xs font-medium text-gray-500 uppercase mb-2">To</p>
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800"
            />
          </div>

          <div>
            <p className="text-xs font-medium text-gray-500 uppercase mb-2">
              Audit Type
            </p>
            <Select options={typeOptions} defaultValue={auditTypeId} onChange={setAuditTypeId} />
          </div>
        </div>
      </ComponentCard>

      {loading && <div className="text-sm text-gray-500">Loading…</div>}
      {error && <div className="text-sm text-red-600">{error}</div>}

      {/* Sections per plant */}
      {dataByPlant.map((p) => {
        const scoreSeries = (p.auditCountScore?.data ?? []).map((d) => ({
          group: String(d.group),
          count: num(d.count),
          score: num(d.score),
        }));

        const created = stackedToSingle(p.carCreatedWeekly, p.plant);
        const late = stackedToSingle(p.lateCarWeekly, p.plant);
        const closing = simpleToSeries(p.closingDaysWeekly);

        // align middle chart by group
        const map = new Map<
          string,
          { createdCar: number; lateCar: number; closingDays: number }
        >();

        for (const x of created)
          map.set(x.group, { createdCar: x.value, lateCar: 0, closingDays: 0 });

        for (const x of late) {
          const v = map.get(x.group) ?? { createdCar: 0, lateCar: 0, closingDays: 0 };
          v.lateCar = x.value;
          map.set(x.group, v);
        }

        for (const x of closing) {
          const v = map.get(x.group) ?? { createdCar: 0, lateCar: 0, closingDays: 0 };
          v.closingDays = x.value;
          map.set(x.group, v);
        }

        const middleChartData = Array.from(map.entries())
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([group, v]) => ({ group, ...v }));

        // KPIs derived
        const lastScore = scoreSeries[scoreSeries.length - 1]?.score;
        const prevScore = scoreSeries[scoreSeries.length - 2]?.score;
        const scoreDelta =
          lastScore != null && prevScore != null ? lastScore - prevScore : undefined;

        const score12w = avg(lastN(scoreSeries, 12).map((d) => d.score));
        const lastWeekLabel = scoreSeries[scoreSeries.length - 1]?.group;

        const closingLast = closing[closing.length - 1]?.value;
        const closingPrev = closing[closing.length - 2]?.value;
        const closingDelta =
          closingLast != null && closingPrev != null ? closingLast - closingPrev : undefined;

        const closing12w = avg(lastN(closing, 12).map((d) => d.value));

        return (
          <ComponentCard
            key={p.plant}
            title={toTitle(p.plant)}
          >
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
              {/* Left chart */}
              <div className="xl:col-span-5">
                {scoreSeries.length ? (
                  <ComboAuditCountScoreD3
                    data={scoreSeries}
                    height={340}
                    // if you have a fixed target score, set it here:
                    // targetScore={70}
                  />
                ) : (
                  <div className="text-sm text-gray-500">No audits data.</div>
                )}
              </div>

              {/* Middle chart */}
              <div className="xl:col-span-5">
                {middleChartData.length ? (
                  <MultiBarLineD3 data={middleChartData} height={340} />
                ) : (
                  <div className="text-sm text-gray-500">No CAR/closing data.</div>
                )}

                <div className="mt-2 text-xs text-gray-500">
                  Bars: CAR created (blue) + Late CAR (orange). Line: closing days (light blue).
                  If you need “Open CAR snapshot per week”, that requires a new backend endpoint.
                </div>
              </div>

              {/* Right KPI panel */}
              <div className="xl:col-span-2 border-l border-gray-200 dark:border-gray-700 pl-4">
                <KpiSidePanel
                  auditScore12w={score12w}
                  auditScoreLast={lastScore}
                  auditScoreDelta={scoreDelta}
                  lastWeekLabel={lastWeekLabel}
                  closingDays12w={closing12w}
                  closingDaysLast={closingLast}
                  closingDaysDelta={closingDelta}
                />
              </div>
            </div>

            {/* Small legend like a report */}
            <div className="mt-4 flex flex-wrap gap-4 text-xs text-gray-600">
              <span className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded"
                  style={{ background: "#0B3D91" }}
                />
                Audits / CAR Created
              </span>
              <span className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded"
                  style={{ background: "#F97316" }}
                />
                Score / Late CAR
              </span>
              <span className="flex items-center gap-2">
                <span
                  className="inline-block h-1 w-6 rounded"
                  style={{ background: "#60A5FA" }}
                />
                Closing days
              </span>
              <span className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded"
                  style={{ background: PLANT_COLORS[p.plant] ?? "#9CA3AF" }}
                />
                Plant color: {toTitle(p.plant)}
              </span>
            </div>
          </ComponentCard>
        );
      })}
    </div>
  );
}