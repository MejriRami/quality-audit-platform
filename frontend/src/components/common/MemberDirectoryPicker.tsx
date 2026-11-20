// MemberDirectoryPicker — searchable Northwind directory picker with a
// manual-entry fallback, used for auditee selection on audit create/edit.
//
// Backed by GET /org-directory/members, which always reads a local mirror
// table (never the live MCP) — see app/services/org_member_directory.py in
// the backend. Only ~20% of active Northwind staff have an email on file in the
// directory, so manual typing must always stay available: this component
// never forces a directory match, it just makes picking a known person
// faster and less error-prone when they are listed.
//
// UX note: the dropdown opens on focus even before typing anything (showing
// a handful of directory names) — that's the field's only real "this is a
// live search, not a plain text box" signal, alongside the search icon and
// caption below. Without it, nothing distinguishes this from a normal input
// until the auditor happens to start typing.
import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import axiosInstance from "../../services/axiosInstance";

export interface DirectoryMember {
  people_id: number;
  full_name: string;
  email: string;
  work_unit_name?: string | null;
  role_name?: string | null;
}

export interface PickedAuditee {
  email: string;
  people_id?: number | null;
}

interface MemberDirectoryPickerProps {
  value: PickedAuditee[];
  onChange: (next: PickedAuditee[]) => void;
  /** Validates a manually-typed email before it's added as a chip. */
  isValidManualEmail?: (email: string) => boolean;
  placeholder?: string;
}

export function MemberDirectoryPicker({
  value,
  onChange,
  isValidManualEmail = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email),
  placeholder = "Search by name, email, or role — or type an email and press Enter",
}: MemberDirectoryPickerProps) {
  const [members, setMembers] = useState<DirectoryMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [manualError, setManualError] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    axiosInstance
      .get<DirectoryMember[]>("/org-directory/members")
      .then((res) => {
        if (!cancelled) setMembers(res.data);
      })
      .catch(() => {
        // Directory unreachable/stale on the backend side too (its own
        // fallback already failed) — degrade to manual-entry-only, never
        // block this form.
        if (!cancelled) setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedEmails = useMemo(
    () => new Set(value.map((v) => v.email.toLowerCase())),
    [value],
  );

  // With no query yet, still surface the first handful of directory names
  // on focus — this is what makes the field read as "searchable" rather
  // than a plain input, before the auditor has typed a single character.
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const pool = members.filter((m) => !selectedEmails.has(m.email.toLowerCase()));
    if (!q) return pool.slice(0, 6);
    return pool
      .filter(
        (m) =>
          m.full_name.toLowerCase().includes(q) ||
          m.email.toLowerCase().includes(q) ||
          (m.role_name || "").toLowerCase().includes(q),
      )
      .slice(0, 8);
  }, [members, query, selectedEmails]);

  function addMember(member: DirectoryMember) {
    onChange([...value, { email: member.email.toLowerCase(), people_id: member.people_id }]);
    setQuery("");
    setOpen(false);
  }

  function addManualEmail() {
    const email = query.trim().toLowerCase();
    if (!email) return;
    if (!isValidManualEmail(email)) {
      setManualError("Enter a valid email address.");
      return;
    }
    if (selectedEmails.has(email)) {
      setManualError("This person is already added.");
      return;
    }
    onChange([...value, { email, people_id: null }]);
    setQuery("");
    setManualError("");
    setOpen(false);
  }

  function removeAt(index: number) {
    onChange(value.filter((_, i) => i !== index));
  }

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        // Auto-commit a valid, not-yet-added email left in the search box
        // once focus leaves the whole picker (e.g. clicking Submit) --
        // previously, typing an email here without pressing Enter or
        // clicking a suggestion never reached `value`, so the form still
        // saw an empty auditee list even though the box looked filled.
        const email = query.trim().toLowerCase();
        if (email && isValidManualEmail(email) && !selectedEmails.has(email)) {
          onChange([...value, { email, people_id: null }]);
          setQuery("");
        }
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [query, value, selectedEmails, isValidManualEmail, onChange]);

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setManualError("");
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              if (query.trim() && matches.length > 0) addMember(matches[0]);
              else addManualEmail();
            }
          }}
          placeholder={placeholder}
          className="h-11 w-full rounded-lg border border-gray-300 bg-transparent pl-9 pr-4 py-2.5 text-sm shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-none focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
        />
      </div>
      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
        🔍 Searches the Northwind staff directory as you type — anyone not listed can still be added by email.
      </p>

      {open && (
        <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-900">
          {loading ? (
            <div className="px-3 py-2.5 text-xs text-gray-500 dark:text-gray-400">
              Loading directory…
            </div>
          ) : matches.length > 0 ? (
            <ul className="max-h-56 overflow-auto py-1">
              {!query.trim() && (
                <li className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                  Directory — type to filter
                </li>
              )}
              {matches.map((m) => (
                <li key={m.people_id}>
                  <button
                    type="button"
                    onClick={() => addMember(m)}
                    className="flex w-full flex-col items-start px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-white/5"
                  >
                    <span className="font-medium text-gray-800 dark:text-white/90">
                      {m.full_name}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {m.email}
                      {m.role_name ? ` — ${m.role_name}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : query.trim() ? (
            <div className="px-3 py-2.5 text-xs text-gray-500 dark:text-gray-400">
              {loadError
                ? "Directory unavailable right now — "
                : "Not found in the directory — "}
              press Enter to add "{query.trim()}" as a manually-typed email.
            </div>
          ) : (
            <div className="px-3 py-2.5 text-xs text-gray-500 dark:text-gray-400">
              {loadError
                ? "Directory unavailable right now — type an email manually."
                : "No more directory matches — type a name or email to search."}
            </div>
          )}
        </div>
      )}

      {manualError && <p className="mt-1.5 text-xs text-rose-500">{manualError}</p>}

      {value.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {value.map((auditee, index) => (
            <span
              key={`${auditee.email}-${index}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-700 dark:border-gray-700 dark:bg-white/5 dark:text-gray-300"
              title={auditee.people_id ? "From Northwind directory" : "Manually entered"}
            >
              {auditee.email}
              {!auditee.people_id && (
                <span className="text-gray-400 dark:text-gray-500">(manual)</span>
              )}
              <button
                type="button"
                onClick={() => removeAt(index)}
                className="text-gray-400 hover:text-rose-500 dark:text-gray-500"
                aria-label={`Remove ${auditee.email}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
