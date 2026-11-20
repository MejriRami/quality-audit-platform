/**
 * KpiDashboard.tsx
 * Dark-mode aware. Tooltip hugs the cursor. All 12 KPIs.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import { createPortal } from "react-dom";
import { useTheme } from "../../context/ThemeContext";
import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

type ReferenceLine = { value: number; label?: string };
type KpiStackedResponse = {
  groupBy: string;
  stackBy: string;
  unit?: "hours" | "count" | "score";
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
  gradeLegend?: string[];
  scoringProfile?: string;
};
type PlannedExecutionResponse = {
  groupBy: string;
  unitLeft: "count";
  unitRight: "days";
  data: Array<{
    group: string;
    planned: number;
    actual: number;
    executed: number;
    delayDays: number;
  }>;
};
type KpiSimpleSeriesResponse = {
  groupBy: string;
  unit: "days" | "count" | "score";
  data: Array<{ group: string; value: number }>;
  referenceLines?: ReferenceLine[];
  gradeLines?: Array<{ value: number; label: string }>;
  gradeLegend?: string[];
  scoringProfile?: string;
};
type PlantOverviewResponse = {
  groupBy: "plant";
  groupedMetrics: {
    unit: "count";
    keys: string[];
    data: Array<{ group: string; [k: string]: number | string }>;
  };
  auditCountScoreByPlant: KpiCountScoreResponse;
  details: Array<{
    group: string;
    totalCars: number;
    closedCars: number;
    openCars: number;
    lateOpenCars: number;
    audits: number;
    avgScore: number;
    closureRate: number;
    lateOpenRate: number;
  }>;
};
type FocusTypeScoreResponse = KpiSimpleSeriesResponse & {
  auditCounts: Array<{ group: string; value: number }>;
};
type ChartSection = "audits" | "car" | "score";
type AuditType = { id: number; value: string };

// ─────────────────────────────────────────────────────────────────────────────
// Theme
// ─────────────────────────────────────────────────────────────────────────────

type Theme = {
  bg: string;
  surface: string;
  border: string;
  text: string;
  muted: string;
  subtle: string;
  gridLine: string;
  axisStroke: string;
  skeletonA: string;
  skeletonB: string;
};

const LIGHT: Theme = {
  bg: "#f4f6f9",
  surface: "#ffffff",
  border: "#e8edf4",
  text: "#0f172a",
  muted: "#64748b",
  subtle: "#94a3b8",
  gridLine: "#f1f5f9",
  axisStroke: "#e2e8f0",
  skeletonA: "#f1f5f9",
  skeletonB: "#e8edf4",
};
const DARK: Theme = {
  bg: "#0f172a",
  surface: "#1e293b",
  border: "#334155",
  text: "#f1f5f9",
  muted: "#94a3b8",
  subtle: "#64748b",
  gridLine: "#1e293b",
  axisStroke: "#334155",
  skeletonA: "#1e293b",
  skeletonB: "#263347",
};

// ─────────────────────────────────────────────────────────────────────────────
// Palette
// ─────────────────────────────────────────────────────────────────────────────

const PLANT_PALETTE: Record<string, string> = {
  atlas: "#2563eb",
  carthage: "#0891b2",
  medina: "#d97706",
  monterrey: "#059669",
  tianjin: "#7c3aed",
  kunshan: "#dc2626",
  chennai: "#9333ea",
  frankfort: "#ea580c",
  rayones: "#64748b",
  daegu: "#0284c7",
  anhui: "#16a34a",
  galeana: "#c026d3",
  poitiers: "#b45309",
  loire: "#475569",
};
const FALLBACK_COLORS = [
  "#2563eb",
  "#0891b2",
  "#d97706",
  "#059669",
  "#7c3aed",
  "#dc2626",
  "#9333ea",
  "#ea580c",
  "#0284c7",
  "#16a34a",
];

const C_BLUE = "#2563eb";
const C_AMBER = "#d97706";
const C_GREEN = "#059669";
const C_RED = "#dc2626";
const METRIC_COLORS: Record<string, string> = {
  totalCars: C_BLUE,
  closedCars: C_GREEN,
  openCars: C_AMBER,
  lateOpenCars: C_RED,
  audits: "#7c3aed",
};
const FOCUS_TYPE_LABELS: Record<string, string> = {
  vda: "VDA",
  plantManagerIATF: "Plant Manager IATF",
  isoIatf: "ISO / IATF",
  usageOfGlasses: "Usage of Glasses",
};

const toTitle = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const toLabel = (s: string) =>
  toTitle(s.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " "));
const focusTypeLabel = (s: string) => FOCUS_TYPE_LABELS[s] ?? toLabel(s);
const isHiddenGuideLabel = (label?: string) => {
  const n = (label ?? "").replace(/\s+/g, "").toLowerCase();
  return n.includes("target") || n.includes("max");
};
const hideRefLine = (rl: ReferenceLine) => {
  const n = (rl.label ?? "").replace(/\s+/g, "").toLowerCase();
  return (
    isHiddenGuideLabel(rl.label) ||
    (rl.value === 140 && (n.includes("min") || n.includes("mn")))
  );
};
const toYmd = (d: Date) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};
const defaultDateRange = () => {
  const now = new Date();
  const to = toYmd(now);
  // Rolling 12 months including current month.
  const fromDate = new Date(now.getFullYear(), now.getMonth() - 11, 1);
  const from = toYmd(fromDate);
  return { from, to };
};

// ─────────────────────────────────────────────────────────────────────────────
// Fetch
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = (import.meta as any).env?.VITE_API_URL as string | undefined;
async function fetchJson<T>(path: string): Promise<T> {
  if (!API_BASE) throw new Error("VITE_API_URL is not set.");
  const res = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  const txt = await res.text();
  if (!res.ok) throw new Error(`${res.status}: ${txt.slice(0, 200)}`);
  return JSON.parse(txt) as T;
}

// ─────────────────────────────────────────────────────────────────────────────
// Resize
// ─────────────────────────────────────────────────────────────────────────────

function useContainerWidth(ref: React.RefObject<Element>) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tooltip — fixed, hugs cursor (8px offset), flips when near edges
// ─────────────────────────────────────────────────────────────────────────────

type TT = { x: number; y: number; html: string; visible: boolean };

function useTooltip() {
  const [tt, setTt] = useState<TT>({ x: 0, y: 0, html: "", visible: false });
  const show = useCallback(
    (ev: MouseEvent, html: string) =>
      setTt({ x: ev.clientX, y: ev.clientY, html, visible: true }),
    [],
  );
  const hide = useCallback(() => setTt((t) => ({ ...t, visible: false })), []);

  useEffect(() => {
    if (!tt.visible) return;
    const onViewportChange = () => setTt((t) => ({ ...t, visible: false }));
    window.addEventListener("scroll", onViewportChange, true);
    window.addEventListener("resize", onViewportChange, true);
    return () => {
      window.removeEventListener("scroll", onViewportChange, true);
      window.removeEventListener("resize", onViewportChange, true);
    };
  }, [tt.visible]);

  const Tooltip = useMemo(
    () =>
      function TooltipEl() {
        if (!tt.visible) return null;
        const PAD = 12;
        const TW = 260;
        const TH = 120;
        const vw = typeof window !== "undefined" ? window.innerWidth : 1400;
        const vh = typeof window !== "undefined" ? window.innerHeight : 900;
        let left = tt.x + PAD;
        let top = tt.y + PAD;
        if (left + TW > vw - PAD) left = tt.x - TW - PAD;
        if (top + TH > vh - PAD) top = tt.y - TH - PAD;
        left = Math.max(PAD, Math.min(left, vw - TW - PAD));
        top = Math.max(PAD, Math.min(top, vh - TH - PAD));
        return (
          <div
            style={{
              position: "fixed",
              left,
              top,
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 5,
              padding: "7px 11px",
              fontSize: 11.5,
              fontFamily: "'IBM Plex Sans',sans-serif",
              color: "#f1f5f9",
              pointerEvents: "none",
              zIndex: 9999,
              boxShadow: "0 2px 12px rgba(0,0,0,0.25)",
              lineHeight: 1.6,
              maxWidth: TW,
              minWidth: 110,
            }}
            dangerouslySetInnerHTML={{ __html: tt.html }}
          />
        );
      },
    [tt],
  );

  return { show, hide, Tooltip };
}

// ─────────────────────────────────────────────────────────────────────────────
// D3 helpers
// ─────────────────────────────────────────────────────────────────────────────

function styleAxis(
  g: d3.Selection<SVGGElement, unknown, null, undefined>,
  t: Theme,
) {
  g.select(".domain").attr("stroke", t.axisStroke);
  g.selectAll<SVGLineElement, unknown>("line").attr("stroke", t.axisStroke);
  g.selectAll<SVGTextElement, unknown>("text")
    .attr("font-size", 10)
    .attr("font-family", "'IBM Plex Sans',sans-serif")
    .attr("fill", t.subtle);
}

function addGrid(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  yScale: d3.ScaleLinear<number, number>,
  left: number,
  chartW: number,
  t: Theme,
) {
  svg
    .append("g")
    .attr("transform", `translate(${left},0)`)
    .call(
      d3
        .axisLeft(yScale)
        .ticks(5)
        .tickSize(-chartW)
        .tickFormat(() => ""),
    )
    .call((g) => {
      g.select(".domain").remove();
      g.selectAll("line").attr("stroke", t.gridLine);
    });
}

function compactTickLabel(raw: string) {
  const monthMatch = raw.match(/^(\d{4})-(\d{2})$/);
  if (monthMatch) {
    const y = Number(monthMatch[1]);
    const m = Number(monthMatch[2]) - 1;
    if (!Number.isNaN(y) && !Number.isNaN(m) && m >= 0 && m <= 11) {
      return new Date(y, m, 1).toLocaleDateString("en-US", {
        month: "long",
        year: "numeric",
      });
    }
  }
  if (raw.length <= 10) return raw;
  if (/^\d{4}-W\d{1,2}$/.test(raw)) return raw;
  return `${raw.slice(0, 10)}...`;
}

function drawBottomBandAxis(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  x: d3.ScaleBand<string>,
  H: number,
  bottom: number,
  t: Theme,
) {
  const domain = x.domain();
  const ticks = domain;
  const needsRotate = domain.length > 7 || x.bandwidth() < 32;
  const axis = d3
    .axisBottom(x)
    .tickSizeOuter(0)
    .tickValues(ticks)
    .tickFormat((d) => compactTickLabel(String(d)));
  svg
    .append("g")
    .attr("transform", `translate(0,${H - bottom})`)
    .call(axis as any)
    .call((g) => {
      styleAxis(g, t);
      if (needsRotate) {
        g.selectAll<SVGTextElement, unknown>("text")
          .attr("transform", "rotate(-32)")
          .style("text-anchor", "end");
      }
    });
}

function makeGrad(
  svg: d3.Selection<SVGSVGElement, unknown, null, undefined>,
  id: string,
  color: string,
  opTop = 1,
  opBot = 0.4,
) {
  const defs = svg.select<SVGDefsElement>("defs").empty()
    ? svg.append("defs")
    : svg.select<SVGDefsElement>("defs");
  const g = defs
    .append("linearGradient")
    .attr("id", id)
    .attr("x1", "0")
    .attr("y1", "0")
    .attr("x2", "0")
    .attr("y2", "1");
  g.append("stop")
    .attr("offset", "0%")
    .attr("stop-color", color)
    .attr("stop-opacity", opTop);
  g.append("stop")
    .attr("offset", "100%")
    .attr("stop-color", color)
    .attr("stop-opacity", opBot);
}

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton
// ─────────────────────────────────────────────────────────────────────────────

function Skeleton({ h = 300, t }: { h?: number; t: Theme }) {
  return (
    <div
      style={{
        height: h,
        borderRadius: 4,
        background: `linear-gradient(90deg,${t.skeletonA} 25%,${t.skeletonB} 50%,${t.skeletonA} 75%)`,
        backgroundSize: "200% 100%",
        animation: "shimmer 1.6s infinite",
      }}
    />
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Chart: Stacked Bar
// ─────────────────────────────────────────────────────────────────────────────

function StackedBar({
  data,
  keys,
  unit = "count",
  referenceLines = [],
  height = 300,
  t,
}: {
  data: Array<{ group: string; [k: string]: number | string }>;
  keys: string[];
  unit?: "hours" | "count";
  referenceLines?: ReferenceLine[];
  height?: number;
  t: Theme;
}) {
  const wRef = useRef<HTMLDivElement>(null);
  const sRef = useRef<SVGSVGElement>(null);
  const cw = useContainerWidth(wRef as any);
  const { show, hide, Tooltip } = useTooltip();

  useEffect(() => {
    if (!sRef.current || !cw || !data?.length || !keys?.length) return;
    const svg = d3.select(sRef.current);
    svg.selectAll("*").remove();
    const W = cw,
      H = height,
      m = { top: 24, right: 16, bottom: 58, left: 48 };
    svg
      .attr("width", W)
      .attr("height", H)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .style("overflow", "visible");
    svg.append("defs");

    const rows = data.map((d) => {
      const o: any = { ...d };
      keys.forEach((k) => (o[k] = Number(o[k] ?? 0)));
      return o;
    });
    const series = d3.stack<any>().keys(keys)(rows);
    const yMax = d3.max(series, (s) => d3.max(s, (d) => d[1])) ?? 0;
    const x = d3
      .scaleBand<string>()
      .domain(rows.map((d) => String(d.group)))
      .range([m.left, W - m.right])
      .padding(0.22);
    const y = d3
      .scaleLinear()
      .domain([0, yMax])
      .nice()
      .range([H - m.bottom, m.top]);

    addGrid(svg, y, m.left, W - m.left - m.right, t);
    const getCol = (k: string, i: number) =>
      PLANT_PALETTE[k] ?? FALLBACK_COLORS[i % FALLBACK_COLORS.length];

    series.forEach((s, i) => {
      const col = getCol(s.key, i);
      svg
        .append("g")
        .selectAll("rect")
        .data(s)
        .join("rect")
        .attr("fill", col)
        .attr("x", (d: any) => x(String(d.data.group))!)
        .attr("y", (d: any) => y(d[1]))
        .attr("height", (d: any) => Math.max(0, y(d[0]) - y(d[1])))
        .attr("width", x.bandwidth())
        .attr("rx", i === keys.length - 1 ? 3 : 0)
        .on("mousemove", (ev: MouseEvent, d: any) => {
          const v = Number(d.data[s.key] ?? 0);
          show(
            ev,
            `<span style="color:${col};font-weight:600">${toTitle(s.key)}</span><br/>` +
              `<span style="color:#94a3b8;font-size:11px">${d.data.group}</span><br/>` +
              `<b>${unit === "hours" ? v.toFixed(1) + " h" : v}</b>`,
          );
        })
        .on("mouseleave", hide);
    });

    svg
      .append("g")
      .selectAll("text")
      .data(rows)
      .join("text")
      .attr("x", (d: any) => x(String(d.group))! + x.bandwidth() / 2)
      .attr("y", (d: any) => {
        const tot = keys.reduce((s, k) => s + Number(d[k] ?? 0), 0);
        return y(tot) - 5;
      })
      .attr("text-anchor", "middle")
      .attr("font-size", 10)
      .attr("font-family", "'IBM Plex Sans',sans-serif")
      .attr("fill", t.subtle)
      .text((d: any) => {
        const tot = keys.reduce((s, k) => s + Number(d[k] ?? 0), 0);
        return unit === "hours"
          ? `${Math.round(tot)}h`
          : String(Math.round(tot));
      });

    referenceLines
      .filter((rl) => !hideRefLine(rl))
      .forEach((rl) => {
        const yv = y(rl.value),
          col = rl.label?.toLowerCase().includes("min") ? C_AMBER : C_GREEN;
        svg
          .append("line")
          .attr("x1", m.left)
          .attr("x2", W - m.right)
          .attr("y1", yv)
          .attr("y2", yv)
          .attr("stroke", col)
          .attr("stroke-width", 1.5)
          .attr("stroke-dasharray", "5 3");
        if (rl.label)
          svg
            .append("text")
            .attr("x", W - m.right - 4)
            .attr("y", yv - 5)
            .attr("text-anchor", "end")
            .attr("font-size", 10)
            .attr("font-family", "'IBM Plex Sans',sans-serif")
            .attr("fill", col)
            .text(rl.label);
      });

    drawBottomBandAxis(svg, x, H, m.bottom, t);
    svg
      .append("g")
      .attr("transform", `translate(${m.left},0)`)
      .call(d3.axisLeft(y).ticks(5))
      .call((g) => styleAxis(g, t));
  }, [data, keys, unit, height, referenceLines, cw, t]);

  if (!data?.length) return <EmptyState t={t} />;
  return (
    <div ref={wRef} style={{ position: "relative" }}>
      <svg ref={sRef} />
      <Tooltip />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Chart: Simple Bar
// ─────────────────────────────────────────────────────────────────────────────

function SimpleBar({
  data,
  unit,
  referenceLines = [],
  gradeLines = [],
  height = 300,
  accent = C_BLUE,
  t,
}: {
  data: Array<{ group: string; value: number }>;
  unit: string;
  referenceLines?: ReferenceLine[];
  gradeLines?: Array<{ value: number; label: string }>;
  height?: number;
  accent?: string;
  t: Theme;
}) {
  const wRef = useRef<HTMLDivElement>(null),
    sRef = useRef<SVGSVGElement>(null);
  const cw = useContainerWidth(wRef as any);
  const { show, hide, Tooltip } = useTooltip();

  useEffect(() => {
    if (!sRef.current || !cw || !data?.length) return;
    const svg = d3.select(sRef.current);
    svg.selectAll("*").remove();
    const W = cw,
      H = height,
      m = { top: 24, right: 16, bottom: 44, left: 52 };
    svg
      .attr("width", W)
      .attr("height", H)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .style("overflow", "visible");
    svg.append("defs");
    const visRL = referenceLines.filter((r) => !hideRefLine(r));
    const yMax = Math.max(
      d3.max(data, (d) => d.value) ?? 0,
      ...visRL.map((r) => r.value),
      ...gradeLines.map((r) => r.value),
    );
    const x = d3
      .scaleBand<string>()
      .domain(data.map((d) => d.group))
      .range([m.left, W - m.right])
      .padding(0.3);
    const y = d3
      .scaleLinear()
      .domain([0, yMax])
      .nice()
      .range([H - m.bottom, m.top]);
    addGrid(svg, y, m.left, W - m.left - m.right, t);
    gradeLines
      .filter((gl) => !isHiddenGuideLabel(gl.label))
      .forEach((gl) => {
        svg
          .append("line")
          .attr("x1", m.left)
          .attr("x2", W - m.right)
          .attr("y1", y(gl.value))
          .attr("y2", y(gl.value))
          .attr("stroke", t.axisStroke)
          .attr("stroke-dasharray", "4 3");
        svg
          .append("text")
          .attr("x", m.left + 6)
          .attr("y", y(gl.value) - 5)
          .attr("font-size", 10)
          .attr("font-family", "'IBM Plex Sans',sans-serif")
          .attr("fill", t.subtle)
          .text(gl.label);
      });
    const gid = `sb-${Math.random().toString(36).slice(2)}`;
    makeGrad(svg, gid, accent, 0.95, 0.4);
    svg
      .append("g")
      .selectAll("rect")
      .data(data)
      .join("rect")
      .attr("fill", `url(#${gid})`)
      .attr("x", (d) => x(d.group)!)
      .attr("width", x.bandwidth())
      .attr("y", (d) => y(d.value))
      .attr("height", (d) => y(0) - y(d.value))
      .attr("rx", 3)
      .on("mousemove", (ev: MouseEvent, d: any) => {
        show(
          ev,
          `<span style="color:#94a3b8;font-size:11px">${d.group}</span><br/>` +
            `<b>${unit === "days" ? d.value.toFixed(2) + " days" : d.value.toFixed(1)}</b>`,
        );
      })
      .on("mouseleave", hide);
    svg
      .append("g")
      .selectAll("text")
      .data(data)
      .join("text")
      .attr("x", (d) => x(d.group)! + x.bandwidth() / 2)
      .attr("y", (d) => y(d.value) - 5)
      .attr("text-anchor", "middle")
      .attr("font-size", 9)
      .attr("font-family", "'IBM Plex Sans',sans-serif")
      .attr("fill", t.subtle)
      .text((d) =>
        unit === "days" ? d.value.toFixed(1) : String(Math.round(d.value)),
      );
    visRL.forEach((rl) => {
      svg
        .append("line")
        .attr("x1", m.left)
        .attr("x2", W - m.right)
        .attr("y1", y(rl.value))
        .attr("y2", y(rl.value))
        .attr("stroke", C_GREEN)
        .attr("stroke-width", 1.5)
        .attr("stroke-dasharray", "5 3");
      if (rl.label)
        svg
          .append("text")
          .attr("x", W - m.right - 4)
          .attr("y", y(rl.value) - 5)
          .attr("text-anchor", "end")
          .attr("font-size", 10)
          .attr("font-family", "'IBM Plex Sans',sans-serif")
          .attr("fill", C_GREEN)
          .text(rl.label);
    });
    svg
      .append("g")
      .attr("transform", `translate(0,${H - m.bottom})`)
      .call(d3.axisBottom(x).tickSizeOuter(0))
      .call((g) => styleAxis(g, t));
    svg
      .append("g")
      .attr("transform", `translate(${m.left},0)`)
      .call(d3.axisLeft(y).ticks(5))
      .call((g) => styleAxis(g, t));
  }, [data, unit, height, referenceLines, gradeLines, cw, accent, t]);

  if (!data?.length) return <EmptyState t={t} />;
  return (
    <div ref={wRef} style={{ position: "relative" }}>
      <svg ref={sRef} />
      <Tooltip />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Chart: Category Bar
// ─────────────────────────────────────────────────────────────────────────────

function CategoryBar({
  data,
  unit,
  referenceLines = [],
  gradeLines = [],
  colorByGroup = false,
  height = 300,
  t,
}: {
  data: Array<{ group: string; value: number }>;
  unit: string;
  referenceLines?: ReferenceLine[];
  gradeLines?: Array<{ value: number; label: string }>;
  colorByGroup?: boolean;
  height?: number;
  t: Theme;
}) {
  const wRef = useRef<HTMLDivElement>(null),
    sRef = useRef<SVGSVGElement>(null);
  const cw = useContainerWidth(wRef as any);
  const { show, hide, Tooltip } = useTooltip();

  useEffect(() => {
    if (!sRef.current || !cw || !data?.length) return;
    const svg = d3.select(sRef.current);
    svg.selectAll("*").remove();
    const W = cw,
      H = height,
      m = { top: 24, right: 16, bottom: 68, left: 52 };
    const sorted = [...data].sort((a, b) => b.value - a.value);
    const visRL = referenceLines.filter((r) => !hideRefLine(r));
    const refMax = visRL.length ? Math.max(...visRL.map((r) => r.value)) : 0;
    const gradeMax = gradeLines.length
      ? Math.max(...gradeLines.map((r) => r.value))
      : 0;
    svg
      .attr("width", W)
      .attr("height", H)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .style("overflow", "visible");
    svg.append("defs");
    const x = d3
      .scaleBand<string>()
      .domain(sorted.map((d) => d.group))
      .range([m.left, W - m.right])
      .padding(0.28);
    const y = d3
      .scaleLinear()
      .domain([
        0,
        Math.max(d3.max(sorted, (d) => d.value) ?? 0, refMax, gradeMax),
      ])
      .nice()
      .range([H - m.bottom, m.top]);
    addGrid(svg, y, m.left, W - m.left - m.right, t);
    gradeLines
      .filter((gl) => !isHiddenGuideLabel(gl.label))
      .forEach((gl) => {
        svg
          .append("line")
          .attr("x1", m.left)
          .attr("x2", W - m.right)
          .attr("y1", y(gl.value))
          .attr("y2", y(gl.value))
          .attr("stroke", t.axisStroke)
          .attr("stroke-dasharray", "4 3");
        svg
          .append("text")
          .attr("x", m.left + 6)
          .attr("y", y(gl.value) - 5)
          .attr("font-size", 10)
          .attr("font-family", "'IBM Plex Sans',sans-serif")
          .attr("fill", t.subtle)
          .text(gl.label);
      });
    visRL.forEach((rl) => {
      svg
        .append("line")
        .attr("x1", m.left)
        .attr("x2", W - m.right)
        .attr("y1", y(rl.value))
        .attr("y2", y(rl.value))
        .attr("stroke", C_AMBER)
        .attr("stroke-width", 1.5)
        .attr("stroke-dasharray", "5 3");
      if (rl.label)
        svg
          .append("text")
          .attr("x", W - m.right - 4)
          .attr("y", y(rl.value) - 5)
          .attr("text-anchor", "end")
          .attr("font-size", 10)
          .attr("font-family", "'IBM Plex Sans',sans-serif")
          .attr("fill", C_AMBER)
          .text(rl.label);
    });
    sorted.forEach((d, i) => {
      const fill = colorByGroup
        ? (PLANT_PALETTE[d.group] ??
          FALLBACK_COLORS[i % FALLBACK_COLORS.length])
        : C_BLUE;
      const gid = `cb-${i}-${Math.random().toString(36).slice(2, 6)}`;
      makeGrad(svg, gid, fill, 0.95, 0.4);
      svg
        .append("rect")
        .attr("fill", `url(#${gid})`)
        .attr("x", x(d.group)!)
        .attr("width", x.bandwidth())
        .attr("y", y(d.value))
        .attr("height", y(0) - y(d.value))
        .attr("rx", 3)
        .on("mousemove", (ev: MouseEvent) => {
          show(
            ev,
            `<span style="color:${fill};font-weight:600">${toTitle(d.group)}</span><br/>` +
              `<b>${unit === "days" ? d.value.toFixed(2) + " days" : d.value}</b>`,
          );
        })
        .on("mouseleave", hide);
      svg
        .append("text")
        .attr("x", x(d.group)! + x.bandwidth() / 2)
        .attr("y", y(d.value) - 5)
        .attr("text-anchor", "middle")
        .attr("font-size", 9)
        .attr("font-family", "'IBM Plex Sans',sans-serif")
        .attr("fill", t.subtle)
        .text(unit === "days" ? d.value.toFixed(1) : String(d.value));
    });
    svg
      .append("g")
      .attr("transform", `translate(0,${H - m.bottom})`)
      .call(
        d3
          .axisBottom(x)
          .tickSizeOuter(0)
          .tickFormat((d) => toTitle(String(d))),
      )
      .call((g) => {
        styleAxis(g, t);
        g.selectAll<SVGTextElement, unknown>("text")
          .attr("transform", "rotate(-30)")
          .style("text-anchor", "end");
      });
    svg
      .append("g")
      .attr("transform", `translate(${m.left},0)`)
      .call(d3.axisLeft(y).ticks(5))
      .call((g) => styleAxis(g, t));
  }, [data, unit, height, referenceLines, gradeLines, colorByGroup, cw, t]);

  if (!data?.length) return <EmptyState t={t} />;
  return (
    <div ref={wRef} style={{ position: "relative" }}>
      <svg ref={sRef} />
      <Tooltip />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Chart: Combo Bar + Line
// ─────────────────────────────────────────────────────────────────────────────

function GroupedBar({
  data,
  keys,
  unit = "count",
  colorMap,
  height = 320,
  t,
}: {
  data: Array<{ group: string; [k: string]: number | string }>;
  keys: string[];
  unit?: "count" | "score";
  colorMap?: Record<string, string>;
  height?: number;
  t: Theme;
}) {
  const wRef = useRef<HTMLDivElement>(null),
    sRef = useRef<SVGSVGElement>(null);
  const cw = useContainerWidth(wRef as any);
  const { show, hide, Tooltip } = useTooltip();

  useEffect(() => {
    if (!sRef.current || !cw || !data?.length || !keys?.length) return;
    const svg = d3.select(sRef.current);
    svg.selectAll("*").remove();
    const W = cw,
      H = height,
      m = { top: 24, right: 16, bottom: 62, left: 52 };
    svg
      .attr("width", W)
      .attr("height", H)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .style("overflow", "visible");

    const rows = data.map((d) => {
      const out: Record<string, number | string> = { group: d.group };
      keys.forEach((k) => {
        out[k] = Number(d[k] ?? 0);
      });
      return out;
    });
    const yMax =
      d3.max(rows, (r) => d3.max(keys, (k) => Number(r[k] ?? 0)) ?? 0) ?? 0;

    const x0 = d3
      .scaleBand<string>()
      .domain(rows.map((d) => String(d.group)))
      .range([m.left, W - m.right])
      .padding(0.24);
    const x1 = d3
      .scaleBand<string>()
      .domain(keys)
      .range([0, x0.bandwidth()])
      .padding(0.16);
    const y = d3
      .scaleLinear()
      .domain([0, yMax])
      .nice()
      .range([H - m.bottom, m.top]);

    addGrid(svg, y, m.left, W - m.left - m.right, t);

    const group = svg
      .append("g")
      .selectAll("g")
      .data(rows)
      .join("g")
      .attr("transform", (d) => `translate(${x0(String(d.group))},0)`);

    group
      .selectAll("rect")
      .data((d) =>
        keys.map((k) => ({
          plant: String(d.group),
          key: k,
          value: Number(d[k] ?? 0),
        })),
      )
      .join("rect")
      .attr("x", (d) => x1(d.key)!)
      .attr("y", (d) => y(d.value))
      .attr("width", x1.bandwidth())
      .attr("height", (d) => y(0) - y(d.value))
      .attr("rx", 3)
      .attr(
        "fill",
        (d, i) =>
          colorMap?.[d.key] ??
          METRIC_COLORS[d.key] ??
          FALLBACK_COLORS[i % FALLBACK_COLORS.length],
      )
      .on("mousemove", (ev: MouseEvent, d: any) => {
        const color = colorMap?.[d.key] ?? METRIC_COLORS[d.key] ?? C_BLUE;
        show(
          ev,
          `<span style="color:${color};font-weight:600">${toTitle(d.plant)}</span><br/>` +
            `${toLabel(d.key)}: <b>${unit === "score" ? d.value.toFixed(2) : d.value}</b>`,
        );
      })
      .on("mouseleave", hide);

    svg
      .append("g")
      .attr("transform", `translate(0,${H - m.bottom})`)
      .call(
        d3
          .axisBottom(x0)
          .tickSizeOuter(0)
          .tickFormat((d) => toTitle(String(d))),
      )
      .call((g) => {
        styleAxis(g, t);
        g.selectAll<SVGTextElement, unknown>("text")
          .attr("transform", "rotate(-30)")
          .style("text-anchor", "end");
      });
    svg
      .append("g")
      .attr("transform", `translate(${m.left},0)`)
      .call(d3.axisLeft(y).ticks(5))
      .call((g) => styleAxis(g, t));
  }, [data, keys, unit, colorMap, height, cw, t, show, hide]);

  if (!data?.length) return <EmptyState t={t} />;
  return (
    <div ref={wRef} style={{ position: "relative" }}>
      <svg ref={sRef} />
      <Tooltip />
    </div>
  );
}

function ComboBarLine({
  data,
  gradeLines = [],
  height = 300,
  t,
}: {
  data: Array<{ group: string; count: number; score: number }>;
  gradeLines?: Array<{ value: number; label: string }>;
  height?: number;
  t: Theme;
}) {
  const wRef = useRef<HTMLDivElement>(null),
    sRef = useRef<SVGSVGElement>(null);
  const cw = useContainerWidth(wRef as any);
  const { show, hide, Tooltip } = useTooltip();

  useEffect(() => {
    if (!sRef.current || !cw || !data?.length) return;
    const svg = d3.select(sRef.current);
    svg.selectAll("*").remove();
    const W = cw,
      H = height,
      m = { top: 24, right: 62, bottom: 58, left: 52 };
    svg
      .attr("width", W)
      .attr("height", H)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .style("overflow", "visible");
    svg.append("defs");
    const x = d3
      .scaleBand<string>()
      .domain(data.map((d) => d.group))
      .range([m.left, W - m.right])
      .padding(0.28);
    const yL = d3
      .scaleLinear()
      .domain([0, d3.max(data, (d) => d.count) ?? 0])
      .nice()
      .range([H - m.bottom, m.top]);
    const rightMax = Math.max(
      100,
      d3.max(data, (d) => d.score) ?? 0,
      ...gradeLines.map((g) => g.value),
    );
    const yR = d3
      .scaleLinear()
      .domain([0, rightMax])
      .nice()
      .range([H - m.bottom, m.top]);
    addGrid(svg, yL, m.left, W - m.left - m.right, t);
    gradeLines
      .filter((gl) => !isHiddenGuideLabel(gl.label))
      .forEach((gl) => {
        svg
          .append("line")
          .attr("x1", m.left)
          .attr("x2", W - m.right)
          .attr("y1", yR(gl.value))
          .attr("y2", yR(gl.value))
          .attr("stroke", t.axisStroke)
          .attr("stroke-dasharray", "4 3");
        svg
          .append("text")
          .attr("x", W - m.right - 6)
          .attr("y", yR(gl.value) + 4)
          .attr("text-anchor", "end")
          .attr("font-size", 9)
          .attr("font-family", "'IBM Plex Sans',sans-serif")
          .attr("fill", t.subtle)
          .text(gl.label);
      });
    const gid = `cbl-${Math.random().toString(36).slice(2)}`;
    makeGrad(svg, gid, C_BLUE, 0.85, 0.25);
    svg
      .append("g")
      .selectAll("rect")
      .data(data)
      .join("rect")
      .attr("fill", `url(#${gid})`)
      .attr("x", (d) => x(d.group)!)
      .attr("width", x.bandwidth())
      .attr("y", (d) => yL(d.count))
      .attr("height", (d) => yL(0) - yL(d.count))
      .attr("rx", 3)
      .on("mousemove", (ev: MouseEvent, d: any) => {
        show(
          ev,
          `<span style="color:#94a3b8;font-size:11px">${d.group}</span><br/>` +
            `Count: <span style="font-weight:600;color:${C_BLUE}">${d.count}</span><br/>` +
            `Score: <span style="font-weight:600;color:${C_AMBER}">${d.score.toFixed(1)}</span>`,
        );
      })
      .on("mouseleave", hide);
    const lineGen = d3
      .line<(typeof data)[0]>()
      .x((d) => x(d.group)! + x.bandwidth() / 2)
      .y((d) => yR(d.score))
      .curve(d3.curveMonotoneX);
    svg
      .append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", C_AMBER)
      .attr("stroke-width", 2)
      .attr("d", lineGen);
    svg
      .append("g")
      .selectAll("circle")
      .data(data)
      .join("circle")
      .attr("cx", (d) => x(d.group)! + x.bandwidth() / 2)
      .attr("cy", (d) => yR(d.score))
      .attr("r", 3.5)
      .attr("fill", C_AMBER)
      .attr("stroke", t.surface)
      .attr("stroke-width", 1.5);
    drawBottomBandAxis(svg, x, H, m.bottom, t);
    svg
      .append("g")
      .attr("transform", `translate(${m.left},0)`)
      .call(d3.axisLeft(yL).ticks(5))
      .call((g) => styleAxis(g, t));
    svg
      .append("g")
      .attr("transform", `translate(${W - m.right},0)`)
      .call(d3.axisRight(yR).ticks(5))
      .call((g) => {
        styleAxis(g, t);
        g.selectAll<SVGTextElement, unknown>("text").attr("fill", C_AMBER);
      });
  }, [data, height, gradeLines, cw, t]);

  if (!data?.length) return <EmptyState t={t} />;
  return (
    <div ref={wRef} style={{ position: "relative" }}>
      <svg ref={sRef} />
      <Tooltip />
    </div>
  );
}

function PlannedExecutionChart({
  data,
  height = 320,
  t,
}: {
  data: Array<{
    group: string;
    planned: number;
    actual: number;
    executed: number;
    delayDays: number;
  }>;
  height?: number;
  t: Theme;
}) {
  const wRef = useRef<HTMLDivElement>(null),
    sRef = useRef<SVGSVGElement>(null);
  const cw = useContainerWidth(wRef as any);
  const { show, hide, Tooltip } = useTooltip();

  useEffect(() => {
    if (!sRef.current || !cw || !data?.length) return;
    const svg = d3.select(sRef.current);
    svg.selectAll("*").remove();
    const W = cw,
      H = height,
      m = { top: 24, right: 62, bottom: 58, left: 52 };
    svg
      .attr("width", W)
      .attr("height", H)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .style("overflow", "visible");
    svg.append("defs");

    const x0 = d3
      .scaleBand<string>()
      .domain(data.map((d) => d.group))
      .range([m.left, W - m.right])
      .padding(0.24);
    const x1 = d3
      .scaleBand<string>()
      .domain(["planned", "actual", "executed"])
      .range([0, x0.bandwidth()])
      .padding(0.15);
    const yL = d3
      .scaleLinear()
      .domain([
        0,
        d3.max(data, (d) => Math.max(d.planned, d.actual, d.executed)) ?? 0,
      ])
      .nice()
      .range([H - m.bottom, m.top]);
    const minDelay = Math.min(0, d3.min(data, (d) => d.delayDays) ?? 0);
    const maxDelay = Math.max(0, d3.max(data, (d) => d.delayDays) ?? 0);
    const yR = d3
      .scaleLinear()
      .domain([minDelay, maxDelay])
      .nice()
      .range([H - m.bottom, m.top]);

    addGrid(svg, yL, m.left, W - m.left - m.right, t);

    const groups = svg
      .append("g")
      .selectAll("g")
      .data(data)
      .join("g")
      .attr("transform", (d) => `translate(${x0(d.group)},0)`);

    groups
      .selectAll("rect")
      .data((d) => [
        {
          key: "planned",
          value: d.planned,
          group: d.group,
          planned: d.planned,
          actual: d.actual,
          executed: d.executed,
          delayDays: d.delayDays,
        },
        {
          key: "actual",
          value: d.actual,
          group: d.group,
          planned: d.planned,
          actual: d.actual,
          executed: d.executed,
          delayDays: d.delayDays,
        },
        {
          key: "executed",
          value: d.executed,
          group: d.group,
          planned: d.planned,
          actual: d.actual,
          executed: d.executed,
          delayDays: d.delayDays,
        },
      ])
      .join("rect")
      .attr("x", (d) => x1(d.key)!)
      .attr("y", (d) => yL(d.value))
      .attr("width", x1.bandwidth())
      .attr("height", (d) => yL(0) - yL(d.value))
      .attr("rx", 3)
      .attr("fill", (d) =>
        d.key === "planned"
          ? C_BLUE
          : d.key === "actual"
            ? "#7c3aed"
            : "#0ea5a5",
      )
      .on("mousemove", (ev: MouseEvent, d: any) => {
        show(
          ev,
          `<span style="font-weight:600">${d.group}</span><br/>` +
            `Planned: <b style="color:${C_BLUE}">${d.planned}</b>` +
            `<br/>Actual: <b style="color:#7c3aed">${d.actual}</b>` +
            `<br/>Executed: <b style="color:#0ea5a5">${d.executed}</b>` +
            `<br/>Delay: <b style="color:${C_AMBER}">${Number(d.delayDays).toFixed(1)} days</b>`,
        );
      })
      .on("mouseleave", hide);

    const line = d3
      .line<(typeof data)[0]>()
      .x((d) => x0(d.group)! + x0.bandwidth() / 2)
      .y((d) => yR(d.delayDays))
      .curve(d3.curveMonotoneX);

    svg
      .append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", C_AMBER)
      .attr("stroke-width", 2)
      .attr("d", line);
    svg
      .append("g")
      .selectAll("circle")
      .data(data)
      .join("circle")
      .attr("cx", (d) => x0(d.group)! + x0.bandwidth() / 2)
      .attr("cy", (d) => yR(d.delayDays))
      .attr("r", 3.5)
      .attr("fill", C_AMBER)
      .attr("stroke", t.surface)
      .attr("stroke-width", 1.5);

    drawBottomBandAxis(svg, x0, H, m.bottom, t);
    svg
      .append("g")
      .attr("transform", `translate(${m.left},0)`)
      .call(d3.axisLeft(yL).ticks(5))
      .call((g) => styleAxis(g, t));
    svg
      .append("g")
      .attr("transform", `translate(${W - m.right},0)`)
      .call(d3.axisRight(yR).ticks(5))
      .call((g) => {
        styleAxis(g, t);
        g.selectAll<SVGTextElement, unknown>("text").attr("fill", C_AMBER);
      });
    if (minDelay < 0) {
      svg
        .append("line")
        .attr("x1", m.left)
        .attr("x2", W - m.right)
        .attr("y1", yR(0))
        .attr("y2", yR(0))
        .attr("stroke", t.axisStroke)
        .attr("stroke-dasharray", "3 3");
    }
  }, [data, height, cw, t, show, hide]);

  if (!data?.length) return <EmptyState t={t} />;
  return (
    <div ref={wRef} style={{ position: "relative" }}>
      <svg ref={sRef} />
      <Tooltip />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// UI atoms
// ─────────────────────────────────────────────────────────────────────────────

function Legend({ keys, t }: { keys: string[]; t: Theme }) {
  if (!keys?.length) return null;
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "8px 14px",
        marginBottom: 12,
      }}
    >
      {keys.map((k, i) => (
        <div key={k} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: 2,
              background:
                METRIC_COLORS[k] ??
                PLANT_PALETTE[k] ??
                FALLBACK_COLORS[i % FALLBACK_COLORS.length],
            }}
          />
          <span
            style={{
              fontSize: 11,
              fontFamily: "'IBM Plex Sans',sans-serif",
              color: t.muted,
            }}
          >
            {focusTypeLabel(k)}
          </span>
        </div>
      ))}
    </div>
  );
}

function GradeLegend({
  items,
  profile,
  t,
}: {
  items?: string[];
  profile?: string;
  t: Theme;
}) {
  if (!items?.length) return null;
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        marginBottom: 10,
      }}
    >
      {profile ? (
        <span
          style={{
            fontSize: 10,
            color: t.text,
            border: `1px solid ${t.border}`,
            borderRadius: 999,
            padding: "3px 9px",
            background: t.bg,
            fontWeight: 600,
          }}
        >
          {profile}
        </span>
      ) : null}
      {items.map((item) => (
        <span
          key={item}
          style={{
            fontSize: 10,
            color: t.muted,
            border: `1px solid ${t.border}`,
            borderRadius: 999,
            padding: "3px 9px",
            background: t.bg,
          }}
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function EmptyState({ t }: { t: Theme }) {
  return (
    <div
      style={{
        height: 80,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: t.subtle,
        fontSize: 12,
        fontFamily: "'IBM Plex Sans',sans-serif",
        border: `1px dashed ${t.border}`,
        borderRadius: 6,
        letterSpacing: "0.04em",
      }}
    >
      No data available
    </div>
  );
}

function KpiCard({
  title,
  badge,
  children,
  loading,
  accentColor,
  t,
}: {
  title: string;
  badge?: string;
  children: React.ReactNode;
  loading?: boolean;
  accentColor?: string;
  t: Theme;
}) {
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!expanded) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [expanded]);

  return (
    <>
      <div
        style={{
          background: t.surface,
          border: `1px solid ${t.border}`,
          borderTop: `2px solid ${accentColor ?? t.border}`,
          borderRadius: 8,
          padding: "20px 22px",
          boxShadow: `0 1px 3px rgba(0,0,0,0.06),0 4px 16px rgba(0,0,0,0.04)`,
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: 11,
              fontWeight: 600,
              fontFamily: "'IBM Plex Sans',sans-serif",
              letterSpacing: "0.07em",
              textTransform: "uppercase",
              color: t.text,
            }}
          >
            {title}
          </h3>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {badge && (
              <span
                style={{
                  fontSize: 9,
                  fontFamily: "'IBM Plex Sans',sans-serif",
                  background: t.bg,
                  border: `1px solid ${t.border}`,
                  borderRadius: 999,
                  padding: "2px 8px",
                  color: t.muted,
                  letterSpacing: "0.05em",
                }}
              >
                {badge}
              </span>
            )}
            <button
              type="button"
              onClick={() => setExpanded(true)}
              style={{
                fontSize: 10,
                fontFamily: "'IBM Plex Sans',sans-serif",
                background: t.bg,
                border: `1px solid ${t.border}`,
                borderRadius: 6,
                padding: "4px 8px",
                color: t.muted,
                letterSpacing: "0.03em",
                cursor: "pointer",
              }}
            >
              Expand
            </button>
          </div>
        </div>
        {loading ? <Skeleton h={300} t={t} /> : children}
      </div>
      {expanded &&
        !loading &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            role="dialog"
            aria-modal="true"
            onClick={() => setExpanded(false)}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(2,6,23,0.65)",
              zIndex: 9999,
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "center",
              padding: 24,
              overflowY: "auto",
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                width: "min(1400px, 96vw)",
                maxHeight: "calc(100vh - 48px)",
                overflow: "auto",
                background: t.surface,
                border: `1px solid ${t.border}`,
                borderTop: `2px solid ${accentColor ?? t.border}`,
                borderRadius: 10,
                padding: "20px 22px",
                boxShadow: "0 18px 60px rgba(0,0,0,0.35)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 14,
                }}
              >
                <h3
                  style={{
                    margin: 0,
                    fontSize: 12,
                    fontWeight: 700,
                    fontFamily: "'IBM Plex Sans',sans-serif",
                    letterSpacing: "0.07em",
                    textTransform: "uppercase",
                    color: t.text,
                  }}
                >
                  {title}
                </h3>
                <button
                  type="button"
                  onClick={() => setExpanded(false)}
                  style={{
                    fontSize: 11,
                    background: t.bg,
                    border: `1px solid ${t.border}`,
                    borderRadius: 6,
                    padding: "5px 9px",
                    color: t.muted,
                    cursor: "pointer",
                  }}
                >
                  Close
                </button>
              </div>
              {children}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

function StatCard({
  label,
  value,
  sub,
  color,
  trend,
  t,
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
  trend?: "up" | "down";
  t: Theme;
}) {
  const tCol = trend === "up" ? "#16a34a" : trend === "down" ? C_RED : t.subtle;
  const tIcon = trend === "up" ? "↑" : trend === "down" ? "↓" : "";
  return (
    <div
      style={{
        background: t.surface,
        border: `1px solid ${t.border}`,
        borderRadius: 8,
        padding: "20px 22px",
        boxShadow: "0 1px 3px rgba(0,0,0,0.06),0 4px 16px rgba(0,0,0,0.04)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 2,
          background: color ?? t.border,
        }}
      />
      <div
        style={{
          fontSize: 10,
          fontFamily: "'IBM Plex Sans',sans-serif",
          color: t.subtle,
          letterSpacing: "0.09em",
          textTransform: "uppercase",
          marginBottom: 10,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: "'IBM Plex Sans',sans-serif",
          fontSize: 30,
          fontWeight: 700,
          color: t.text,
          letterSpacing: "-0.03em",
          lineHeight: 1,
          display: "flex",
          alignItems: "baseline",
          gap: 8,
        }}
      >
        {value}
        {tIcon && (
          <span style={{ fontSize: 14, color: tCol, fontWeight: 500 }}>
            {tIcon}
          </span>
        )}
      </div>
      {sub && (
        <div
          style={{
            fontSize: 11,
            color: t.subtle,
            marginTop: 6,
            fontFamily: "'IBM Plex Sans',sans-serif",
          }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}

function SectionHeader({
  label,
  open,
  onToggle,
  t,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
  t: Theme;
}) {
  return (
    <button
      onClick={onToggle}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        background: "none",
        border: "none",
        cursor: "pointer",
        padding: "14px 0",
        width: "100%",
      }}
    >
      <div style={{ flex: 1, height: 1, background: t.border }} />
      <span
        style={{
          fontFamily: "'IBM Plex Sans',sans-serif",
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: t.subtle,
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </span>
      <span style={{ color: t.subtle, fontSize: 10 }}>{open ? "▲" : "▼"}</span>
      <div style={{ flex: 1, height: 1, background: t.border }} />
    </button>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  t,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
  t: Theme;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label
        style={{
          fontSize: 9,
          fontFamily: "'IBM Plex Sans',sans-serif",
          color: t.subtle,
          letterSpacing: "0.1em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: t.surface,
          border: `1px solid ${t.border}`,
          borderRadius: 6,
          padding: "7px 10px",
          fontSize: 12,
          fontFamily: "'IBM Plex Sans',sans-serif",
          color: t.text,
          outline: "none",
          cursor: "pointer",
          minWidth: 140,
          boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function FilterDate({
  label,
  value,
  onChange,
  t,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  t: Theme;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label
        style={{
          fontSize: 9,
          fontFamily: "'IBM Plex Sans',sans-serif",
          color: t.subtle,
          letterSpacing: "0.1em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </label>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: t.surface,
          border: `1px solid ${t.border}`,
          borderRadius: 6,
          padding: "7px 10px",
          fontSize: 12,
          fontFamily: "'IBM Plex Sans',sans-serif",
          color: t.text,
          outline: "none",
          minWidth: 140,
          colorScheme: t.bg === "#0f172a" ? "dark" : "light",
          boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
        }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Dark mode toggle button
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const PLANT_OPTIONS = [
  { value: "all", label: "All Plants" },
  { value: "atlas", label: "Atlas" },
  { value: "carthage", label: "Carthage" },
  { value: "medina", label: "Medina" },
  { value: "monterrey", label: "Monterrey" },
  { value: "tianjin", label: "Tianjin" },
  { value: "kunshan", label: "Kunshan" },
  { value: "chennai", label: "Chennai" },
  { value: "frankfort", label: "Frankfort" },
  { value: "rayones", label: "Rayones" },
  { value: "daegu", label: "Daegu" },
  { value: "anhui", label: "Anhui" },
  { value: "galeana", label: "Galeana" },
  { value: "poitiers", label: "Poitiers" },
  { value: "loire", label: "Loire" },
];
const INTERVAL_OPTIONS = [
  { value: "month", label: "Monthly" },
  { value: "week", label: "Weekly" },
];
const DATE_BASIS_OPTIONS = [
  { value: "planned", label: "Planned Date" },
  { value: "actual", label: "Actual Date" },
];

// Two separate reports: audits run in this app (live), and the history
// imported from Monday (frozen). Monday never recorded exact planning /
// execution dates, audit hours or scores, so KPIs built on those are hidden
// for it instead of showing a misleading 100%.
type DataSource = "app" | "monday";
const DATA_SOURCE_OPTIONS: Array<{ value: DataSource; label: string }> = [
  { value: "app", label: "App audits (live)" },
  { value: "monday", label: "Monday history (frozen)" },
];

type AllData = {
  auditHours?: KpiStackedResponse;
  auditScoreByDate?: KpiSimpleSeriesResponse;
  auditCountScore?: KpiCountScoreResponse;
  auditStatusByPeriod?: KpiStackedResponse;
  auditStatusByPlant?: KpiStackedResponse;
  plannedExecution?: PlannedExecutionResponse;
  auditsByTypePlant?: KpiStackedResponse;
  avgScoreByTypePlant?: KpiStackedResponse;
  avgScoreByPlant?: KpiSimpleSeriesResponse;
  carCount?: KpiStackedResponse;
  lateCar?: KpiStackedResponse;
  avgDaysClose?: KpiSimpleSeriesResponse;
  workingDaysByPlant?: KpiSimpleSeriesResponse;
  openCarByPlant?: KpiSimpleSeriesResponse;
  lateOpenCarByPlant?: KpiSimpleSeriesResponse;
  closedLateCarByPlant?: KpiSimpleSeriesResponse;
  openCarByAudit?: KpiSimpleSeriesResponse;
  plantOverview?: PlantOverviewResponse;
  avgScoreByFocusType?: FocusTypeScoreResponse;
};

// ─────────────────────────────────────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────────────────────────────────────

export default function KpiDashboard() {
  const { theme } = useTheme();
  const dark = theme === "dark";
  const t = dark ? DARK : LIGHT;
  const initialRange = useMemo(() => defaultDateRange(), []);

  const [dataSource, setDataSource] = useState<DataSource>("app");
  const isMonday = dataSource === "monday";
  const [plant, setPlant] = useState("all");
  const [interval, setInterval] = useState("month");
  const [dateBasis, setDateBasis] = useState("planned");
  const [auditTypeId, setAuditTypeId] = useState("all");
  const [auditTypeOptions, setAuditTypeOptions] = useState<
    Array<{ value: string; label: string }>
  >([{ value: "all", label: "All Audit Types" }]);
  const [from, setFrom] = useState(initialRange.from);
  const [to, setTo] = useState(initialRange.to);
  const [data, setData] = useState<AllData>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openSections, setOpenSections] = useState<
    Record<ChartSection, boolean>
  >({ audits: true, car: true, score: true });
  const toggle = (s: ChartSection) =>
    setOpenSections((p) => ({ ...p, [s]: !p[s] }));

  const qs = useMemo(() => {
    const p = new URLSearchParams();
    p.set("data_source", dataSource);
    if (from) p.set("from", from);
    if (to) p.set("to", to);
    if (plant !== "all") p.set("plant", plant);
    if (!isMonday && auditTypeId !== "all") p.set("audit_type_id", auditTypeId);
    return p.toString();
  }, [dataSource, isMonday, from, to, plant, auditTypeId]);

  // The Monday report covers its whole (closed) history by default; the app
  // report goes back to the rolling 12 months.
  const changeDataSource = (next: DataSource) => {
    setDataSource(next);
    setFrom(next === "monday" ? "" : initialRange.from);
    setTo(next === "monday" ? "" : initialRange.to);
  };

  useEffect(() => {
    fetchJson<AuditType[]>("/audit-types/all")
      .then((rows) => {
        const options = rows
          .filter((r) => r?.id && String(r.value ?? "").trim())
          .map((r) => ({
            value: String(r.id),
            label: toLabel(String(r.value)),
          }));
        setAuditTypeOptions([
          { value: "all", label: "All Audit Types" },
          ...options,
        ]);
      })
      .catch(() => {
        setAuditTypeOptions([{ value: "all", label: "All Audit Types" }]);
      });
  }, []);

  useEffect(() => {
    if (from && to && from > to) {
      setError(
        "Invalid date range: 'From' date must be before or equal to 'To'.",
      );
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    Promise.all([
      fetchJson<KpiStackedResponse>(
        `/kpi/audit-hours?interval=${interval}&date_basis=${dateBasis}&${qs}`,
      ),
      fetchJson<KpiSimpleSeriesResponse>(
        `/kpi/audit-score-by-date?interval=${interval}&date_basis=${dateBasis}&${qs}`,
      ),
      fetchJson<KpiCountScoreResponse>(
        `/kpi/audit-count-score?interval=${interval}&date_basis=${dateBasis}&${qs}`,
      ),
      fetchJson<KpiStackedResponse>(
        `/kpi/audit-status-by-period?interval=${interval}&date_basis=${dateBasis}&${qs}`,
      ),
      fetchJson<KpiStackedResponse>(
        `/kpi/audit-status-by-plant?date_basis=${dateBasis}&${qs}`,
      ),
      fetchJson<PlannedExecutionResponse>(
        `/kpi/planned-vs-execution?interval=${interval}&date_basis=${dateBasis}&${qs}`,
      ),
      fetchJson<KpiStackedResponse>(`/kpi/audits-by-type-plant?${qs}`),
      fetchJson<KpiStackedResponse>(
        `/kpi/avg-score-by-type-plant?date_basis=${dateBasis}&${qs}`,
      ),
      fetchJson<KpiSimpleSeriesResponse>(
        `/kpi/avg-audit-score-by-plant?date_basis=${dateBasis}&${qs}`,
      ),
      fetchJson<KpiStackedResponse>(
        `/kpi/car-count?interval=${interval}&${qs}`,
      ),
      fetchJson<KpiStackedResponse>(`/kpi/late-car?interval=${interval}&${qs}`),
      fetchJson<KpiSimpleSeriesResponse>(
        `/kpi/avg-days-close-car?interval=${interval}&${qs}`,
      ),
      fetchJson<KpiSimpleSeriesResponse>(
        `/kpi/working-days-close-car-by-plant?${qs}`,
      ),
      fetchJson<KpiSimpleSeriesResponse>(`/kpi/open-car-by-plant?${qs}`),
      fetchJson<KpiSimpleSeriesResponse>(`/kpi/late-open-car-by-plant?${qs}`),
      fetchJson<KpiSimpleSeriesResponse>(`/kpi/closed-late-car-by-plant?${qs}`),
      fetchJson<KpiSimpleSeriesResponse>(
        `/kpi/open-car-by-audit?${qs}&limit=25`,
      ),
      fetchJson<PlantOverviewResponse>(
        `/kpi/plant-audit-car-overview?date_basis=${dateBasis}&${qs}`,
      ),
      fetchJson<FocusTypeScoreResponse>(
        `/kpi/avg-score-by-focus-type?date_basis=${dateBasis}&${qs}`,
      ),
    ])
      .then(
        ([
          auditHours,
          auditScoreByDate,
          auditCountScore,
          auditStatusByPeriod,
          auditStatusByPlant,
          plannedExecution,
          auditsByTypePlant,
          avgScoreByTypePlant,
          avgScoreByPlant,
          carCount,
          lateCar,
          avgDaysClose,
          workingDaysByPlant,
          openCarByPlant,
          lateOpenCarByPlant,
          closedLateCarByPlant,
          openCarByAudit,
          plantOverview,
          avgScoreByFocusType,
        ]) => {
          setData({
            auditHours,
            auditScoreByDate,
            auditCountScore,
            auditStatusByPeriod,
            auditStatusByPlant,
            plannedExecution,
            auditsByTypePlant,
            avgScoreByTypePlant,
            avgScoreByPlant,
            carCount,
            lateCar,
            avgDaysClose,
            workingDaysByPlant,
            openCarByPlant,
            lateOpenCarByPlant,
            closedLateCarByPlant,
            openCarByAudit,
            plantOverview,
            avgScoreByFocusType,
          });
        },
      )
      .catch((e) => setError(e?.message ?? "Failed to load"))
      .finally(() => setLoading(false));
  }, [qs, interval, dateBasis, from, to]);

  const totalAudits = useMemo(() => {
    const rows = data.auditStatusByPeriod?.data ?? [];
    if (!rows.length) return "-";
    const n = rows.reduce(
      (sum, r) =>
        sum +
        Number(r.planned ?? 0) +
        Number(r.rescheduled ?? 0) +
        Number(r.postponed ?? 0) +
        Number(r.completed ?? 0) +
        Number(r.cancelled ?? 0) +
        Number(r.waiting_for_corrective_actions ?? 0),
      0,
    );
    return n;
  }, [data.auditStatusByPeriod]);
  const statusCount = useCallback(
    (status: string) => {
      const rows = data.auditStatusByPeriod?.data ?? [];
      if (!rows.length) return 0;
      return rows.reduce((sum, r) => sum + Number(r[status] ?? 0), 0);
    },
    [data.auditStatusByPeriod],
  );
  const plannedAudits = useMemo(() => statusCount("planned"), [statusCount]);
  const cancelledAudits = useMemo(
    () => statusCount("cancelled"),
    [statusCount],
  );
  const waitingCarAudits = useMemo(
    () => statusCount("waiting_for_corrective_actions"),
    [statusCount],
  );
  const rescheduledAudits = useMemo(
    () => statusCount("rescheduled"),
    [statusCount],
  );
  const postponedAudits = useMemo(
    () => statusCount("postponed"),
    [statusCount],
  );
  const completedAudits = useMemo(
    () => statusCount("completed"),
    [statusCount],
  );
  const totalCars = useMemo(
    () =>
      data.plantOverview?.details.reduce((s, d) => s + d.totalCars, 0) ?? "-",
    [data.plantOverview],
  );
  const totalClosedCars = useMemo(
    () =>
      data.plantOverview?.details.reduce((s, d) => s + d.closedCars, 0) ?? "-",
    [data.plantOverview],
  );
  const totalOpenCar = useMemo(
    () => data.openCarByPlant?.data.reduce((s, d) => s + d.value, 0) ?? "-",
    [data.openCarByPlant],
  );
  const totalLateCar = useMemo(
    () => data.lateOpenCarByPlant?.data.reduce((s, d) => s + d.value, 0) ?? "-",
    [data.lateOpenCarByPlant],
  );
  const totalClosedLateCar = useMemo(
    () =>
      data.closedLateCarByPlant?.data.reduce((s, d) => s + d.value, 0) ?? "-",
    [data.closedLateCarByPlant],
  );
  const avgScore = useMemo(() => {
    const d = data.auditCountScore?.data ?? [];
    if (!d.length) return "-";
    const totalCount = d.reduce((s, r) => s + Number(r.count ?? 0), 0);
    if (totalCount <= 0) return "-";
    const weightedSum = d.reduce(
      (s, r) => s + Number(r.score ?? 0) * Number(r.count ?? 0),
      0,
    );
    return (weightedSum / totalCount).toFixed(1);
  }, [data.auditCountScore]);
  const closureRate = useMemo(() => {
    if (
      typeof totalCars !== "number" ||
      typeof totalClosedCars !== "number" ||
      totalCars <= 0
    ) {
      return "-";
    }
    return `${((totalClosedCars / totalCars) * 100).toFixed(1)}%`;
  }, [totalCars, totalClosedCars]);
  const carsPerAudit = useMemo(() => {
    if (
      typeof totalCars !== "number" ||
      typeof totalAudits !== "number" ||
      totalAudits <= 0
    ) {
      return "-";
    }
    return (totalCars / totalAudits).toFixed(2);
  }, [totalCars, totalAudits]);
  const avgScoreTypeColorMap = useMemo(() => {
    const keys = data.avgScoreByTypePlant?.keys ?? [];
    return keys.reduce<Record<string, string>>((acc, k, i) => {
      acc[k] = FALLBACK_COLORS[i % FALLBACK_COLORS.length];
      return acc;
    }, {});
  }, [data.avgScoreByTypePlant?.keys]);

  const gs = `
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
    *{box-sizing:border-box;}
    @keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
    @keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
    .kpi-fade{animation:fadeUp 0.28s ease forwards;}
    .kpi-main-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:12px;margin-bottom:4px;}
    .kpi-stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:24px;}
    .kpi-filter-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px;align-items:end;}
    @media (max-width: 1200px){
      .kpi-main-grid{grid-template-columns:1fr;}
    }
    @media (max-width: 640px){
      .kpi-page{padding:18px 12px 28px;}
      .kpi-header{margin-bottom:16px;}
      .kpi-stats-grid{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));}
    }
    ::-webkit-scrollbar{width:5px;height:5px;}
    ::-webkit-scrollbar-track{background:${t.bg};}
    ::-webkit-scrollbar-thumb{background:${t.border};border-radius:3px;}
  `;

  return (
    <>
      <PageMeta
        title="KPI Audits"
        description="Audit performance, compliance trends, and corrective action velocity."
      />
      <style>{gs}</style>
      {/* ── Full-page wrapper that owns the background color ── */}
      <div
        className="kpi-page"
        style={{
          background: "transparent",
          padding: "0 0 20px",
          maxWidth: 1600,
          margin: "0 auto",
          fontFamily: "inherit",
          transition: "background 0.2s,color 0.2s",
        }}
      >
        <PageBreadcrumb
          kicker="Analytics"
          pageTitle="KPI Audits"
          description="Audit performance, compliance trends, and CAR closure velocity across plants."
          actions={
            <span className="rounded-full border border-slate-200/70 bg-white px-3 py-1 text-xs font-semibold text-slate-600 shadow-sm dark:border-slate-800/70 dark:bg-slate-900 dark:text-slate-200">
              {new Date().toLocaleDateString("en-GB", {
                day: "2-digit",
                month: "short",
                year: "numeric",
              })}
            </span>
          }
        />

        {/* Filters */}
        <div
          className="kpi-filter-grid"
          style={{
            background: t.surface,
            border: `1px solid ${t.border}`,
            borderRadius: 8,
            padding: "16px 20px",
            boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
            marginBottom: 24,
          }}
        >
          <FilterSelect
            label="Report"
            value={dataSource}
            onChange={(v) => changeDataSource(v as DataSource)}
            options={DATA_SOURCE_OPTIONS}
            t={t}
          />
          <FilterSelect
            label="Plant"
            value={plant}
            onChange={setPlant}
            options={PLANT_OPTIONS}
            t={t}
          />
          <FilterSelect
            label="Interval"
            value={interval}
            onChange={setInterval}
            options={INTERVAL_OPTIONS}
            t={t}
          />
          {!isMonday && (
            <FilterSelect
              label="Date Basis"
              value={dateBasis}
              onChange={setDateBasis}
              options={DATE_BASIS_OPTIONS}
              t={t}
            />
          )}
          {!isMonday && (
            <FilterSelect
              label="Audit Type"
              value={auditTypeId}
              onChange={setAuditTypeId}
              options={auditTypeOptions}
              t={t}
            />
          )}
          <FilterDate label="From" value={from} onChange={setFrom} t={t} />
          <FilterDate label="To" value={to} onChange={setTo} t={t} />
          {loading && (
            <div
              style={{
                fontSize: 11,
                color: t.subtle,
                alignSelf: "center",
                letterSpacing: "0.06em",
              }}
            >
              Loading…
            </div>
          )}
        </div>

        {isMonday && (
          <div
            style={{
              background: t.surface,
              border: `1px solid ${t.border}`,
              borderLeft: `3px solid ${C_AMBER}`,
              borderRadius: 6,
              padding: "12px 16px",
              marginBottom: 20,
              fontSize: 12,
              color: t.muted,
            }}
          >
            Frozen history imported from Monday. Monday did not record exact
            planning and execution dates, audit hours, scores or audit types,
            so those KPIs are not shown here. Audits run in the app are in the
            "App audits (live)" report.
          </div>
        )}

        {error && (
          <div
            style={{
              background: dark ? "#2d1515" : "#fff5f5",
              border: "1px solid #fecaca",
              borderRadius: 6,
              padding: "12px 16px",
              marginBottom: 20,
              fontSize: 12,
              color: "#b91c1c",
            }}
          >
            {error}
          </div>
        )}

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            marginBottom: 10,
            flexWrap: "wrap",
          }}
        >
          <h2
            style={{
              margin: 0,
              fontSize: 12,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: t.subtle,
            }}
          >
            Executive Snapshot
          </h2>
        </div>

        {/* Stats */}
        <div
          className="kpi-stats-grid"
          style={{
            marginBottom: 24,
          }}
        >
          <StatCard
            label="Total Audits"
            value={totalAudits}
            color={C_BLUE}
            sub="in selected period"
            t={t}
          />
          <StatCard
            label="Planned Audits"
            value={plannedAudits}
            color={C_BLUE}
            sub="status: planned"
            t={t}
          />
          <StatCard
            label="Rescheduled Audits"
            value={rescheduledAudits}
            color="#0f766e"
            sub="status: rescheduled"
            t={t}
          />
          <StatCard
            label="Postponed Audits"
            value={postponedAudits}
            color="#0f766e"
            sub="status: postponed"
            t={t}
          />

          <StatCard
            label="Cancelled Audits"
            value={cancelledAudits}
            color={C_RED}
            sub="status: cancelled"
            t={t}
          />
          <StatCard
            label="Completed Audits"
            value={completedAudits}
            color={C_GREEN}
            sub="status: completed"
            t={t}
          />
          <StatCard
            label="Waiting for CAR"
            value={waitingCarAudits}
            color={C_AMBER}
            sub="status: waiting_for_corrective_actions"
            t={t}
          />

          <StatCard
            label="Total CARs"
            value={totalCars}
            color={C_AMBER}
            sub="created in period"
            t={t}
          />
          <StatCard
            label="Closed CARs"
            value={totalClosedCars}
            color={C_GREEN}
            sub={`closure rate ${closureRate}`}
            t={t}
          />
          <StatCard
            label="Open CARs"
            value={totalOpenCar}
            color={C_AMBER}
            sub="not closed"
            t={t}
          />
          <StatCard
            label="CARs per Audit"
            value={carsPerAudit}
            color={C_BLUE}
            sub="quality workload"
            t={t}
          />

          <StatCard
            label="Late Open CARs"
            value={totalLateCar}
            color={C_RED}
            sub="past due date"
            trend="down"
            t={t}
          />
          <StatCard
            label="Closed Late CARs"
            value={totalClosedLateCar}
            color={C_RED}
            sub="closed after due date"
            t={t}
          />
          {!isMonday && (
            <StatCard
              label="Average Score"
              value={avgScore}
              color={C_GREEN}
              sub="all audits"
              t={t}
            />
          )}
        </div>

        {/* ─── Audit Performance ─── */}
        <SectionHeader
          label="Audit Performance"
          open={openSections.audits}
          onToggle={() => toggle("audits")}
          t={t}
        />
        {openSections.audits && (
          <div className="kpi-fade kpi-main-grid">
            {!isMonday && (
              <KpiCard
                title="Hours of Audits by Date"
                badge="All Plants"
                loading={loading}
                accentColor={C_BLUE}
                t={t}
              >
                <Legend keys={data.auditHours?.keys ?? []} t={t} />
                <StackedBar
                  data={data.auditHours?.data ?? []}
                  keys={data.auditHours?.keys ?? []}
                  unit="hours"
                  referenceLines={data.auditHours?.referenceLines}
                  t={t}
                />
              </KpiCard>
            )}
            <KpiCard
              title="Number of Audits & Score"
              badge="Dual Axis"
              loading={loading}
              accentColor={C_BLUE}
              t={t}
            >
              <GradeLegend
                items={data.auditCountScore?.gradeLegend}
                profile={data.auditCountScore?.scoringProfile}
                t={t}
              />
              <div
                style={{
                  display: "flex",
                  gap: 16,
                  fontSize: 11,
                  color: t.muted,
                  marginBottom: 10,
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: 2,
                      background: C_BLUE,
                      display: "inline-block",
                    }}
                  />
                  Count
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{
                      width: 14,
                      height: 2,
                      background: C_AMBER,
                      display: "inline-block",
                    }}
                  />
                  Score
                </span>
              </div>
              <ComboBarLine
                data={data.auditCountScore?.data ?? []}
                gradeLines={data.auditCountScore?.gradeLines ?? []}
                t={t}
              />
            </KpiCard>
            {!isMonday && (
              <KpiCard
                title="Planned vs Execution (Report Creation)"
                loading={loading}
                accentColor={C_BLUE}
                t={t}
              >
                <div
                  style={{
                    display: "flex",
                    gap: 16,
                    fontSize: 11,
                    color: t.muted,
                    marginBottom: 10,
                  }}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: 2,
                        background: C_BLUE,
                        display: "inline-block",
                      }}
                    />
                    Planned Count
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: 2,
                        background: "#7c3aed",
                        display: "inline-block",
                      }}
                    />
                    Actual Count
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: 2,
                        background: "#0ea5a5",
                        display: "inline-block",
                      }}
                    />
                    Executed/Reported
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span
                      style={{
                        width: 14,
                        height: 2,
                        background: C_AMBER,
                        display: "inline-block",
                      }}
                    />
                    Avg Delay (days)
                  </span>
                </div>
                <PlannedExecutionChart
                  data={data.plannedExecution?.data ?? []}
                  t={t}
                />
              </KpiCard>
            )}
            <KpiCard
              title="Number of Audits & Score by Plant"
              badge="Plant View"
              loading={loading}
              accentColor={C_BLUE}
              t={t}
            >
              <div
                style={{
                  display: "flex",
                  gap: 16,
                  fontSize: 11,
                  color: t.muted,
                  marginBottom: 10,
                }}
              >
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: 2,
                      background: C_BLUE,
                      display: "inline-block",
                    }}
                  />
                  Audits
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{
                      width: 14,
                      height: 2,
                      background: C_AMBER,
                      display: "inline-block",
                    }}
                  />
                  Avg Score
                </span>
              </div>
              <ComboBarLine
                data={data.plantOverview?.auditCountScoreByPlant.data ?? []}
                gradeLines={
                  data.plantOverview?.auditCountScoreByPlant.gradeLines ?? []
                }
                t={t}
              />
            </KpiCard>
            {!isMonday && (
              <KpiCard
                title="Audits per Type per Plant"
                badge="Stacked"
                loading={loading}
                accentColor={C_BLUE}
                t={t}
              >
                <Legend keys={data.auditsByTypePlant?.keys ?? []} t={t} />
                <StackedBar
                  data={data.auditsByTypePlant?.data ?? []}
                  keys={data.auditsByTypePlant?.keys ?? []}
                  unit="count"
                  t={t}
                />
              </KpiCard>
            )}
            <KpiCard
              title="Audit Status by Period"
              badge="Week/Month"
              loading={loading}
              accentColor={C_BLUE}
              t={t}
            >
              <Legend keys={data.auditStatusByPeriod?.keys ?? []} t={t} />
              <StackedBar
                data={data.auditStatusByPeriod?.data ?? []}
                keys={data.auditStatusByPeriod?.keys ?? []}
                unit="count"
                t={t}
              />
            </KpiCard>
            <KpiCard
              title="Audit Status by Plant"
              badge="Selected Period"
              loading={loading}
              accentColor={C_BLUE}
              t={t}
            >
              <Legend keys={data.auditStatusByPlant?.keys ?? []} t={t} />
              <StackedBar
                data={data.auditStatusByPlant?.data ?? []}
                keys={data.auditStatusByPlant?.keys ?? []}
                unit="count"
                t={t}
              />
            </KpiCard>
          </div>
        )}

        {/* Monday history has no scores. */}
        {!isMonday && (
          <>
            {/* ─── Score Analysis ─── */}
            <SectionHeader
              label="Score Analysis"
              open={openSections.score}
              onToggle={() => toggle("score")}
              t={t}
            />
            {openSections.score && (
              <div className="kpi-fade kpi-main-grid">
                <KpiCard
                  title="Audit Score by Date"
                  badge="All Plants · All Types"
                  loading={loading}
                  accentColor={C_GREEN}
                  t={t}
                >
                  <GradeLegend
                    items={data.auditScoreByDate?.gradeLegend}
                    profile={data.auditScoreByDate?.scoringProfile}
                    t={t}
                  />
                  <SimpleBar
                    data={data.auditScoreByDate?.data ?? []}
                    unit="score"
                    gradeLines={data.auditScoreByDate?.gradeLines}
                    accent={C_GREEN}
                    t={t}
                  />
                </KpiCard>
                <KpiCard
                  title="Average Audit Score by Plant"
                  badge="Ranking"
                  loading={loading}
                  accentColor={C_GREEN}
                  t={t}
                >
                  <GradeLegend
                    items={data.avgScoreByPlant?.gradeLegend}
                    profile={data.avgScoreByPlant?.scoringProfile}
                    t={t}
                  />
                  <CategoryBar
                    data={data.avgScoreByPlant?.data ?? []}
                    unit="score"
                    colorByGroup
                    referenceLines={data.avgScoreByPlant?.referenceLines}
                    gradeLines={data.avgScoreByPlant?.gradeLines}
                    t={t}
                  />
                </KpiCard>
                <KpiCard
                  title="Average Score by Audit Type"
                  badge="VDA / PM-IATF / ISO-IATF / Glasses"
                  loading={loading}
                  accentColor={C_GREEN}
                  t={t}
                >
                  <GradeLegend
                    items={data.avgScoreByFocusType?.gradeLegend}
                    profile={data.avgScoreByFocusType?.scoringProfile}
                    t={t}
                  />
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 8,
                      marginBottom: 10,
                    }}
                  >
                    {(data.avgScoreByFocusType?.auditCounts ?? []).map((d) => (
                      <span
                        key={d.group}
                        style={{
                          fontSize: 10,
                          color: t.muted,
                          border: `1px solid ${t.border}`,
                          borderRadius: 999,
                          padding: "3px 8px",
                        }}
                      >
                        {focusTypeLabel(d.group)}: {d.value} audits
                      </span>
                    ))}
                  </div>
                  <SimpleBar
                    data={(data.avgScoreByFocusType?.data ?? []).map((d) => ({
                      ...d,
                      group: focusTypeLabel(d.group),
                    }))}
                    unit="score"
                    gradeLines={data.avgScoreByFocusType?.gradeLines}
                    accent={C_GREEN}
                    t={t}
                  />
                </KpiCard>
                <KpiCard
                  title="Average Score by Audit Type by Plant"
                  badge="Selected Period"
                  loading={loading}
                  accentColor={C_GREEN}
                  t={t}
                >
                  <Legend keys={data.avgScoreByTypePlant?.keys ?? []} t={t} />
                  <GroupedBar
                    data={data.avgScoreByTypePlant?.data ?? []}
                    keys={data.avgScoreByTypePlant?.keys ?? []}
                    unit="score"
                    colorMap={avgScoreTypeColorMap}
                    t={t}
                  />
                </KpiCard>
              </div>
            )}
          </>
        )}

        {/* ─── Corrective Actions ─── */}
        <SectionHeader
          label="Corrective Actions"
          open={openSections.car}
          onToggle={() => toggle("car")}
          t={t}
        />
        {openSections.car && (
          <div className="kpi-fade kpi-main-grid">
            <KpiCard
              title="CARs (Total, Closed, Open, Late Open) & Audits by Plant"
              badge="Grouped"
              loading={loading}
              accentColor={C_AMBER}
              t={t}
            >
              <Legend
                keys={data.plantOverview?.groupedMetrics.keys ?? []}
                t={t}
              />
              <GroupedBar
                data={data.plantOverview?.groupedMetrics.data ?? []}
                keys={data.plantOverview?.groupedMetrics.keys ?? []}
                t={t}
              />
            </KpiCard>
            <KpiCard
              title="CARs by Date"
              badge="Stacked by Plant"
              loading={loading}
              accentColor={C_AMBER}
              t={t}
            >
              <Legend keys={data.carCount?.keys ?? []} t={t} />
              <StackedBar
                data={data.carCount?.data ?? []}
                keys={data.carCount?.keys ?? []}
                unit="count"
                t={t}
              />
            </KpiCard>
            <KpiCard
              title="Late CARs by Period"
              badge="Stacked by Plant"
              loading={loading}
              accentColor={C_RED}
              t={t}
            >
              <Legend keys={data.lateCar?.keys ?? []} t={t} />
              <StackedBar
                data={data.lateCar?.data ?? []}
                keys={data.lateCar?.keys ?? []}
                unit="count"
                t={t}
              />
            </KpiCard>
            <KpiCard
              title="Avg. Days to Close a CAR"
              badge="Calendar Days"
              loading={loading}
              accentColor={C_AMBER}
              t={t}
            >
              <SimpleBar
                data={data.avgDaysClose?.data ?? []}
                unit="days"
                referenceLines={data.avgDaysClose?.referenceLines}
                accent={C_AMBER}
                t={t}
              />
            </KpiCard>
            <KpiCard
              title="Avg. Working Days to Close — by Plant"
              badge="Mon – Fri"
              loading={loading}
              accentColor={C_AMBER}
              t={t}
            >
              <CategoryBar
                data={data.workingDaysByPlant?.data ?? []}
                unit="days"
                referenceLines={data.workingDaysByPlant?.referenceLines}
                colorByGroup
                t={t}
              />
            </KpiCard>
            <KpiCard
              title="Open CARs by Plant"
              badge="Not Closed"
              loading={loading}
              accentColor={C_AMBER}
              t={t}
            >
              <CategoryBar
                data={data.openCarByPlant?.data ?? []}
                unit="count"
                colorByGroup
                t={t}
              />
            </KpiCard>
            <KpiCard
              title="Late Open CARs by Plant"
              badge="Overdue"
              loading={loading}
              accentColor={C_RED}
              t={t}
            >
              <CategoryBar
                data={data.lateOpenCarByPlant?.data ?? []}
                unit="count"
                colorByGroup
                t={t}
              />
            </KpiCard>
            <KpiCard
              title="Closed Late CARs by Plant"
              badge="Closed after due date"
              loading={loading}
              accentColor={C_RED}
              t={t}
            >
              <CategoryBar
                data={data.closedLateCarByPlant?.data ?? []}
                unit="count"
                colorByGroup
                t={t}
              />
            </KpiCard>
            <KpiCard
              title="Open CARs by Audit"
              badge="Top 25"
              loading={loading}
              accentColor={C_AMBER}
              t={t}
            >
              <CategoryBar
                data={data.openCarByAudit?.data ?? []}
                unit="count"
                colorByGroup={false}
                t={t}
              />
            </KpiCard>
          </div>
        )}

        {/* Footer */}
        {/* <div
          style={{
            marginTop: 44,
            paddingTop: 16,
            borderTop: `1px solid ${t.border}`,
            display: "flex",
            justifyContent: "space-between",
            fontSize: 10,
            color: t.subtle,
            letterSpacing: "0.06em",
          }}
        >
          <span>KPI Dashboard · v2</span>
          <span>Audit Intelligence Platform</span>
        </div> */}
      </div>
    </>
  );
}
