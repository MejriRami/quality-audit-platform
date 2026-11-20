import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { BadgeCheck, PlusCircle } from "lucide-react";
import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import { Modal } from "../../components/ui/modal";
import {
  apiErrorMessage,
  createCertification,
  deleteCertification,
  fetchCertificationMe,
  fetchCertificationMeta,
  fetchCertifications,
  labelize,
  updateCertification,
  uploadCertificationDocument,
  type Certification,
  type CertificationInput,
  type CertificationMeta,
} from "../../services/externalCertificationsApi";
import CertificationFormModal, { inputClass, type PendingFile } from "./CertificationFormModal";
import CertificationDocumentsModal from "./CertificationDocumentsModal";

const DOCUMENT_TYPE_CLASS: Record<string, string> = {
  certificate: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  report: "bg-sky-50 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  "report.json for IATF CARA": "bg-violet-50 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  other: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
};
const EXPIRED_CLASS = "bg-rose-50 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300";

// Expiration dates are plain "YYYY-MM-DD" strings, so they compare as text.
const todayIso = () => new Date().toLocaleDateString("en-CA");
const isExpiredCertificate = (c: Certification) =>
  c.document_type === "certificate" &&
  !!c.certification_expiration_date &&
  c.certification_expiration_date < todayIso();

// Rows are grouped by document type, in badge order: valid certificates
// (green), expired certificates (red), reports (blue), IATF CARA .json
// (violet), other, then untyped. Within a group the server order is kept
// (most recently updated first).
const DOCUMENT_TYPE_RANK: Record<string, number> = {
  certificate: 0,
  report: 2,
  "report.json for IATF CARA": 3,
  other: 4,
};
const groupRank = (c: Certification) =>
  isExpiredCertificate(c) ? 1 : (DOCUMENT_TYPE_RANK[c.document_type ?? ""] ?? 5);
const groupByDocumentType = (rows: Certification[]) =>
  rows
    .map((c, i) => ({ c, i }))
    .sort((a, b) => groupRank(a.c) - groupRank(b.c) || a.i - b.i)
    .map(({ c }) => c);

const secondaryButton =
  "rounded-lg border border-[#9ec6df] px-3 py-1.5 text-xs font-semibold text-[#064273] transition hover:bg-[#f6fbff] dark:border-[#0f6ea9] dark:text-[#e1f2ff]";
const dangerButton =
  "rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 transition hover:bg-rose-100 dark:border-rose-900/40 dark:bg-rose-900/20 dark:text-rose-300";

export default function ExternalCertifications() {
  // Edit rights come from the backend: they depend on the Northwind directory role
  // as well as app roles, and portal visitors have no app roles at all.
  const [canEdit, setCanEdit] = useState(false);

  const [meta, setMeta] = useState<CertificationMeta | null>(null);
  const [certs, setCerts] = useState<Certification[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [plant, setPlant] = useState("");

  const [editing, setEditing] = useState<Certification | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Certification | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [viewingDocs, setViewingDocs] = useState<Certification | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setCerts(groupByDocumentType(await fetchCertifications({ search, plant })));
    } catch (err) {
      setLoadError(apiErrorMessage(err, "Failed to load certifications"));
    } finally {
      setLoading(false);
    }
  }, [search, plant]);

  useEffect(() => {
    fetchCertificationMeta()
      .then(setMeta)
      .catch((err) => setLoadError(apiErrorMessage(err, "Failed to load filters")));
    fetchCertificationMe()
      .then((me) => setCanEdit(me.can_edit))
      .catch(() => setCanEdit(false));
  }, []);

  useEffect(() => {
    const t = setTimeout(() => void load(), 250);
    return () => clearTimeout(t);
  }, [load]);

  function openForm(cert: Certification | null) {
    setEditing(cert);
    setShowForm(true);
  }

  async function handleSubmit(input: CertificationInput, files: PendingFile[]) {
    const certId = editing ? (await updateCertification(editing.id, input)).id : (await createCertification(input)).id;
    for (const { file, documentType } of files) {
      await uploadCertificationDocument(certId, file, documentType);
    }
    setShowForm(false);
    toast.success(editing ? "Certification updated" : "Certification created");
    await load();
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteCertification(pendingDelete.id);
      setPendingDelete(null);
      toast.success("Certification deleted");
      await load();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Delete failed"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageMeta title="External Certifications" description="Manage external certifications and their documents." />
      <PageBreadcrumb
        kicker="Certifications"
        pageTitle="External Certifications"
        description="Certifications from external bodies (IATF 16949, ISO 14001...), with their documents and nonconformities."
        actions={
          <>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200/70 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm dark:border-slate-800/70 dark:bg-slate-950/60 dark:text-slate-100">
              <BadgeCheck className="h-3.5 w-3.5" />
              {certs.length} certifications
            </span>
            {canEdit && (
              <button
                type="button"
                onClick={() => openForm(null)}
                disabled={!meta}
                className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-[#064273] to-[#0a5f95] px-4 py-2 text-sm font-semibold text-white transition hover:from-[#05375f] hover:to-[#084d79] disabled:opacity-60"
              >
                <PlusCircle className="h-4 w-4" />
                New certification
              </button>
            )}
          </>
        }
      />

      <section className="rounded-2xl border border-[#b8d3e6] bg-white/95 p-5 shadow-sm dark:border-[#0a5f95] dark:bg-[#072f4a]/80">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_200px]">
          <input
            className={inputClass}
            placeholder="Search name, number, plant..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select className={inputClass} value={plant} onChange={(e) => setPlant(e.target.value)}>
            <option value="">All plants</option>
            {meta?.plants.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        {loadError && <p className="mt-4 text-sm text-rose-600">{loadError}</p>}

        <div className="mt-5 overflow-x-auto rounded-2xl border border-[#dbe8f1] dark:border-[#14486a]">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-[#f6fbff] text-xs uppercase tracking-wide text-[#4b738e] dark:bg-[#08304c] dark:text-[#a9cee5]">
              <tr>
                <th className="px-4 py-3">Certification</th>
                <th className="px-4 py-3">Plant</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Document type</th>
                <th className="px-4 py-3">Certificate scope</th>
                <th className="px-4 py-3">Quality manager</th>
                <th className="px-4 py-3">Expiration</th>
                <th className="px-4 py-3">Docs / NCs</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#edf4f8] text-[#0d3550] dark:divide-[#123f5f] dark:text-[#eaf6ff]">
              {loading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-[#5e8198] dark:text-[#b8dcf2]">
                    Loading certifications...
                  </td>
                </tr>
              ) : certs.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-[#5e8198] dark:text-[#b8dcf2]">
                    No certifications match your filters.
                  </td>
                </tr>
              ) : (
                certs.map((c) => (
                  <tr key={c.id}>
                    <td className="px-4 py-3">
                      <p className="font-medium">{c.name}</p>
                      <p className="text-xs text-[#5d7e94] dark:text-[#a9cee5]">{c.certification_number}</p>
                    </td>
                    <td className="px-4 py-3">{c.plant ?? "—"}</td>
                    <td className="px-4 py-3">{c.certification_type ?? "—"}</td>
                    <td className="px-4 py-3">
                      {c.document_type ? (
                        <span
                          className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${
                            isExpiredCertificate(c) ? EXPIRED_CLASS : (DOCUMENT_TYPE_CLASS[c.document_type] ?? "")
                          }`}
                          title={isExpiredCertificate(c) ? `Expired on ${c.certification_expiration_date}` : undefined}
                        >
                          {labelize(c.document_type)}
                          {isExpiredCertificate(c) && " · Expired"}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="max-w-[260px] px-4 py-3">
                      {c.document_type === "certificate" && c.scope ? (
                        <p className="line-clamp-3 text-xs" title={c.scope}>
                          {c.scope}
                        </p>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3">{c.quality_manager_name ?? "—"}</td>
                    <td
                      className={`whitespace-nowrap px-4 py-3 ${isExpiredCertificate(c) ? "font-semibold text-rose-600 dark:text-rose-300" : ""}`}
                    >
                      {c.certification_expiration_date ?? "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <button
                        type="button"
                        onClick={() => setViewingDocs(c)}
                        className="font-medium text-[#0a5f95] hover:underline dark:text-[#7cc4f2]"
                      >
                        {c.document_count} doc{c.document_count === 1 ? "" : "s"}
                      </button>{" "}
                      / {c.nonconformity_count} NC
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      {canEdit && (
                        <div className="inline-flex gap-2">
                          <button type="button" onClick={() => openForm(c)} disabled={!meta} className={secondaryButton}>
                            Edit
                          </button>
                          <button type="button" onClick={() => setPendingDelete(c)} className={dangerButton}>
                            Delete
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {showForm && meta && canEdit && (
        <CertificationFormModal
          meta={meta}
          editing={editing}
          onSubmit={handleSubmit}
          onCancel={() => setShowForm(false)}
        />
      )}

      {viewingDocs && (
        <CertificationDocumentsModal
          certification={viewingDocs}
          canEdit={canEdit}
          onClose={() => setViewingDocs(null)}
          onChange={() => void load()}
        />
      )}

      {pendingDelete && (
        <Modal isOpen onClose={() => setPendingDelete(null)} className="m-4 max-w-md p-6">
          <h2 className="text-lg font-semibold text-[#064273] dark:text-[#e1f2ff]">Delete certification?</h2>
          <p className="mt-2 text-sm text-[#4b738e] dark:text-[#b8dcf2]">
            This permanently deletes <strong>{pendingDelete.name}</strong>
            {pendingDelete.document_count + pendingDelete.nonconformity_count > 0 && (
              <>
                , along with its {pendingDelete.document_count} document(s) and {pendingDelete.nonconformity_count}{" "}
                nonconformity(ies)
              </>
            )}
            . This cannot be undone.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button type="button" onClick={() => setPendingDelete(null)} className={secondaryButton}>
              Cancel
            </button>
            <button type="button" onClick={() => void confirmDelete()} disabled={deleting} className={dangerButton}>
              {deleting ? "Deleting..." : "Delete"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
