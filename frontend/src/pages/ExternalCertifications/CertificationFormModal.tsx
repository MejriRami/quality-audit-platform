import { useState, type FormEvent, type ReactNode } from "react";
import { Modal } from "../../components/ui/modal";
import {
  apiErrorMessage,
  labelize,
  type Certification,
  type CertificationDocumentType,
  type CertificationInput,
  type CertificationMeta,
} from "../../services/externalCertificationsApi";

export const inputClass =
  "w-full rounded-xl border border-[#9ec6df] px-3 py-2.5 text-sm dark:border-[#0f6ea9] dark:bg-[#09304b] dark:text-white";

const EMPTY: CertificationInput = {
  monday_group: null,
  certification_number: "",
  name: "",
  certification_type: "",
  document_type: null,
  scope: "",
  plant: "",
  quality_manager_name: "",
  quality_manager_email: "",
  external_certification_body: "",
  audit_date: "",
  date_of_last_audit: "",
  next_expected_audit: "",
  certification_expiration_date: "",
  status: "pending_review",
  rejected_reason: "",
  automation_status: "",
  quality_manager_decision: "",
};

function toInput(cert: Certification | null): CertificationInput {
  if (!cert) return EMPTY;
  const editable = Object.keys(EMPTY) as (keyof CertificationInput)[];
  return Object.fromEntries(editable.map((k) => [k, cert[k]])) as CertificationInput;
}

// Empty-string form fields must become null before hitting the API (dates especially).
function toPayload(input: CertificationInput): CertificationInput {
  const clean: Record<string, unknown> = { ...input };
  Object.keys(clean).forEach((k) => {
    if (clean[k] === "") clean[k] = null;
  });
  return clean as CertificationInput;
}

export type PendingFile = { file: File; documentType: string };

type Props = {
  meta: CertificationMeta;
  editing: Certification | null;
  onSubmit: (input: CertificationInput, files: PendingFile[]) => Promise<void>;
  onCancel: () => void;
};

function Field({
  label,
  wide,
  children,
}: {
  label: string;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`block text-sm font-medium text-[#0d3550] dark:text-[#e1f2ff] ${wide ? "sm:col-span-2" : ""}`}>
      <span className="mb-1 block">{label}</span>
      {children}
    </label>
  );
}

export default function CertificationFormModal({ meta, editing, onSubmit, onCancel }: Props) {
  const [form, setForm] = useState<CertificationInput>(toInput(editing));
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof CertificationInput>(key: K, value: CertificationInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function addFiles(fileList: FileList | null) {
    if (!fileList) return;
    setPendingFiles((prev) => [
      ...prev,
      ...Array.from(fileList).map((file) => ({ file, documentType: "" })),
    ]);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onSubmit(toPayload(form), pendingFiles);
    } catch (err) {
      setError(apiErrorMessage(err, "Save failed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal isOpen onClose={onCancel} className="m-4 max-w-3xl p-6">
      <h2 className="text-lg font-semibold text-[#064273] dark:text-[#e1f2ff]">
        {editing ? "Edit certification" : "New certification"}
      </h2>
      <form
        onSubmit={handleSubmit}
        className="mt-4 grid max-h-[70vh] gap-4 overflow-y-auto pr-1 sm:grid-cols-2"
      >
        <Field label="Name *">
          <input required className={inputClass} value={form.name} onChange={(e) => set("name", e.target.value)} />
        </Field>

        <Field label="Certification number">
          <input
            className={inputClass}
            value={form.certification_number ?? ""}
            onChange={(e) => set("certification_number", e.target.value)}
          />
        </Field>

        <Field label="Certification type">
          <input
            className={inputClass}
            list="certification-types"
            value={form.certification_type ?? ""}
            onChange={(e) => set("certification_type", e.target.value)}
          />
          <datalist id="certification-types">
            {meta.certification_types.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </Field>

        <Field label="Plant">
          <input
            className={inputClass}
            list="certification-plants"
            value={form.plant ?? ""}
            onChange={(e) => set("plant", e.target.value)}
          />
          <datalist id="certification-plants">
            {meta.plants.map((p) => (
              <option key={p} value={p} />
            ))}
          </datalist>
        </Field>

        <Field label="Document type">
          <select
            className={inputClass}
            value={form.document_type ?? ""}
            onChange={(e) => set("document_type", (e.target.value || null) as CertificationDocumentType | null)}
          >
            <option value="">—</option>
            {meta.document_types.map((t) => (
              <option key={t} value={t}>
                {labelize(t)}
              </option>
            ))}
          </select>
        </Field>

        {/* Scope only applies to certificates; still shown elsewhere if a value
            already exists (e.g. imported from Monday) so it isn't hidden. */}
        {(form.document_type === "certificate" || form.scope) && (
          <Field label={form.document_type === "certificate" ? "Certificate scope" : "Scope"} wide>
            <textarea
              className={inputClass}
              rows={2}
              value={form.scope ?? ""}
              onChange={(e) => set("scope", e.target.value)}
            />
          </Field>
        )}

        {/* Status, Monday group, rejected reason, quality manager decision,
            audit date and date of last audit were Monday-era fields: no
            longer shown, but kept in the form state so saving a certification
            preserves their stored values. */}

        <Field label="Quality manager name">
          <input
            className={inputClass}
            value={form.quality_manager_name ?? ""}
            onChange={(e) => set("quality_manager_name", e.target.value)}
          />
        </Field>

        <Field label="Quality manager email">
          <input
            type="email"
            className={inputClass}
            value={form.quality_manager_email ?? ""}
            onChange={(e) => set("quality_manager_email", e.target.value)}
          />
        </Field>

        <Field label="External certification body">
          <input
            className={inputClass}
            value={form.external_certification_body ?? ""}
            onChange={(e) => set("external_certification_body", e.target.value)}
          />
        </Field>

        {/* Read by audit planning: P8 (IATF) / P10 (ISO 14001) fire when the
            next external audit is within 4 months. */}
        <Field label="Next expected audit">
          <input
            type="date"
            className={inputClass}
            value={form.next_expected_audit ?? ""}
            onChange={(e) => set("next_expected_audit", e.target.value)}
          />
        </Field>

        <Field label="Certification expiration date">
          <input
            type="date"
            className={inputClass}
            value={form.certification_expiration_date ?? ""}
            onChange={(e) => set("certification_expiration_date", e.target.value)}
          />
        </Field>

        <div className="sm:col-span-2">
          <Field label="Documents">
            <input
              type="file"
              multiple
              className="block w-full text-sm text-[#0d3550] dark:text-[#e1f2ff]"
              onChange={(e) => addFiles(e.target.files)}
            />
          </Field>
          {pendingFiles.length > 0 && (
            <ul className="mt-3 space-y-2">
              {pendingFiles.map((pf, i) => (
                <li
                  key={i}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#dbe8f1] px-3 py-2 dark:border-[#14486a]"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-[#0d3550] dark:text-[#eaf6ff]">{pf.file.name}</p>
                    <input
                      className={`${inputClass} mt-1 py-1.5`}
                      list="certification-document-types"
                      placeholder="Document type (e.g. certificate, report)"
                      value={pf.documentType}
                      onChange={(e) =>
                        setPendingFiles((prev) =>
                          prev.map((f, j) => (j === i ? { ...f, documentType: e.target.value } : f)),
                        )
                      }
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setPendingFiles((prev) => prev.filter((_, j) => j !== i))}
                    className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 transition hover:bg-rose-100 dark:border-rose-900/40 dark:bg-rose-900/20 dark:text-rose-300"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
          <datalist id="certification-document-types">
            <option value="certificate" />
            <option value="report" />
            <option value="report.json for IATF CARA" />
          </datalist>
        </div>

        {error && <p className="text-sm text-rose-600 sm:col-span-2">{error}</p>}

        <div className="flex justify-end gap-2 sm:col-span-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded-xl border border-[#9ec6df] px-4 py-2.5 text-sm font-semibold text-[#064273] transition hover:bg-[#f6fbff] disabled:opacity-60 dark:border-[#0f6ea9] dark:text-[#e1f2ff]"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-xl bg-gradient-to-r from-[#064273] to-[#0a5f95] px-4 py-2.5 text-sm font-semibold text-white transition hover:from-[#05375f] hover:to-[#084d79] disabled:opacity-60"
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
