// DirectoryEmailField — single-value Northwind directory picker for fields like
// "Supervisor Email" that hold exactly one email, not a list. Same backing
// endpoint/fallback behavior as MemberDirectoryPicker (GET
// /org-directory/members, local mirror only, manual entry always allowed
// since only a fraction of Northwind staff have an email on file). This field is
// plain string in/out — the backend column it feeds (e.g.
// audits.supervisor_email) isn't linked via people_id, so there's nothing
// to round-trip beyond the email itself.
//
// Same "how do I know this is a picker" affordances as MemberDirectoryPicker:
// search icon, a persistent caption, and the dropdown opening on focus with
// a few directory names even before typing.
import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import axiosInstance from "../../services/axiosInstance";
import { DirectoryMember } from "./MemberDirectoryPicker";

interface DirectoryEmailFieldProps {
  id?: string;
  value: string;
  onChange: (email: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export function DirectoryEmailField({
  id,
  value,
  onChange,
  placeholder = "Search the Northwind directory, or type an email",
  className,
  disabled = false,
}: DirectoryEmailFieldProps) {
  const [members, setMembers] = useState<DirectoryMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    axiosInstance
      .get<DirectoryMember[]>("/org-directory/members")
      .then((res) => {
        if (!cancelled) setMembers(res.data);
      })
      .catch(() => {
        // Directory unreachable — degrade to a plain text field, same as
        // before this feature existed.
        if (!cancelled) setLoadError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const matches = useMemo(() => {
    const q = value.trim().toLowerCase();
    if (!q) return members.slice(0, 6);
    return members
      .filter(
        (m) =>
          m.full_name.toLowerCase().includes(q) ||
          m.email.toLowerCase().includes(q) ||
          (m.role_name || "").toLowerCase().includes(q),
      )
      .slice(0, 8);
  }, [members, value]);

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
        <input
          id={id}
          type="text"
          value={value}
          disabled={disabled}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder}
          className={
            className ??
            "h-11 w-full rounded-lg border border-[#064273]/20 bg-white pl-9 pr-3 text-sm text-slate-700 outline-none transition focus:border-[#064273] focus:ring-2 focus:ring-[#064273]/20 disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#064273]/40 dark:bg-white/[0.04] dark:text-slate-200"
          }
        />
      </div>
      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
        🔍 Searches the Northwind staff directory as you type — anyone not listed can still be typed manually.
      </p>

      {open && (
        <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg dark:border-gray-700 dark:bg-gray-900">
          {loading ? (
            <div className="px-3 py-2.5 text-xs text-gray-500 dark:text-gray-400">
              Loading directory…
            </div>
          ) : matches.length > 0 ? (
            <ul className="max-h-56 overflow-auto py-1">
              {!value.trim() && (
                <li className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
                  Directory — type to filter
                </li>
              )}
              {matches.map((m) => (
                <li key={m.people_id}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange(m.email);
                      setOpen(false);
                    }}
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
          ) : (
            <div className="px-3 py-2.5 text-xs text-gray-500 dark:text-gray-400">
              {loadError
                ? "Directory unavailable right now — type an email manually."
                : "No directory match — this email will be used as typed."}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
