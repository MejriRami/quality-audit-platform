import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import axiosInstance from "../services/axiosInstance";

export interface DraftAnswerPayload {
  question_id?: number | null;
  draft_row_id?: string | null;
  value?: number | null;
  finding_text?: string;
  request_car?: boolean;
  car_reason?: string;
  silent_box?: boolean;
  documents?: Array<{
    filename: string;
    mimetype: string;
    size: number;
    file_url: string;
  }>;
  process?: string;
  standard_paragraph?: string;
  classification?: string;
  question_text?: string;
}

export interface DraftPayload {
  audit_date?: string;
  start_time?: string;
  end_time?: string;
  strong_points?: string;
  weak_points?: string;
  answers?: DraftAnswerPayload[];
  expected_draft_etag?: string | null;
}

export interface DraftData extends DraftPayload {
  audit_id: number;
  saved_at?: string | null;
  draft_etag?: string | null;
}

interface UseDraftAuditReturn {
  data: DraftData | null;
  loading: boolean;
  saving: boolean;
  lastSavedAt: Date | null;
  saveDraft: (payload: DraftPayload) => void;
  flushSave: (payload: DraftPayload) => Promise<void>;
  clearDraft: () => void;
}

const API_BASE = import.meta.env.VITE_API_URL ?? "";
const DEBOUNCE_MS = 1500;

export function useDraftAudit(auditId: number | "" | null): UseDraftAuditReturn {
  const [data, setData] = useState<DraftData | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<DraftPayload | null>(null);
  const latestDraftEtagRef = useRef<string | null>(null);
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());
  const auditIdRef = useRef(auditId);
  auditIdRef.current = auditId;

  useEffect(() => {
    pendingRef.current = null;
    latestDraftEtagRef.current = null;
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, [auditId]);

  useEffect(() => {
    if (!auditId) {
      setData(null);
      setLastSavedAt(null);
      return;
    }

    let cancelled = false;
    setLoading(true);

    axiosInstance
      .get<DraftData>(`${API_BASE}/audits/${auditId}/draft`)
      .then((res) => {
        if (cancelled) return;
        setData(res.data);
        setLastSavedAt(res.data.saved_at ? new Date(res.data.saved_at) : null);
        latestDraftEtagRef.current = res.data.draft_etag ?? null;
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [auditId]);

  const doSave = useCallback(async (payload: DraftPayload) => {
    const id = auditIdRef.current;
    if (!id) return;

    setSaving(true);
    try {
      const res = await axiosInstance.patch<DraftData>(`${API_BASE}/audits/${id}/draft`, {
        ...payload,
        expected_draft_etag: latestDraftEtagRef.current,
      });
      setData(res.data);
      setLastSavedAt(res.data.saved_at ? new Date(res.data.saved_at) : new Date());
      latestDraftEtagRef.current = res.data.draft_etag ?? null;
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        try {
          const latest = await axiosInstance.get<DraftData>(`${API_BASE}/audits/${id}/draft`);
          latestDraftEtagRef.current = latest.data.draft_etag ?? null;

          const retry = await axiosInstance.patch<DraftData>(`${API_BASE}/audits/${id}/draft`, {
            ...payload,
            expected_draft_etag: latestDraftEtagRef.current,
          });
          setData(retry.data);
          setLastSavedAt(retry.data.saved_at ? new Date(retry.data.saved_at) : new Date());
          latestDraftEtagRef.current = retry.data.draft_etag ?? null;
          return;
        } catch (recoveryErr) {
          console.warn("[useDraftAudit] conflict recovery failed:", recoveryErr);
        }
      }
      console.warn("[useDraftAudit] save failed:", err);
    } finally {
      setSaving(false);
    }
  }, []);

  const queueSave = useCallback(
    (payload: DraftPayload) => {
      saveChainRef.current = saveChainRef.current
        .catch(() => undefined)
        .then(() => doSave(payload));
      return saveChainRef.current;
    },
    [doSave],
  );

  const saveDraft = useCallback(
    (payload: DraftPayload) => {
      pendingRef.current = { ...pendingRef.current, ...payload };
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        if (pendingRef.current) {
          void queueSave(pendingRef.current);
          pendingRef.current = null;
        }
      }, DEBOUNCE_MS);
    },
    [queueSave],
  );

  const flushSave = useCallback(
    async (payload: DraftPayload) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      const pending = pendingRef.current;
      pendingRef.current = null;
      const merged = pending ? { ...pending, ...payload } : payload;
      await queueSave(merged);
    },
    [queueSave],
  );

  const clearDraft = useCallback(() => {
    setData(null);
    setLastSavedAt(null);
    latestDraftEtagRef.current = null;
    pendingRef.current = null;
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return { data, loading, saving, lastSavedAt, saveDraft, flushSave, clearDraft };
}
