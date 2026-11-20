import { useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { Modal } from "../../components/ui/modal";
import {
  apiErrorMessage,
  deleteCertificationDocument,
  fetchCertificationDocuments,
  labelize,
  uploadCertificationDocument,
  type Certification,
  type CertificationDocument,
} from "../../services/externalCertificationsApi";
import { inputClass } from "./CertificationFormModal";

type Props = {
  certification: Certification;
  canEdit: boolean;
  onClose: () => void;
  onChange: () => void;
};

export default function CertificationDocumentsModal({ certification, canEdit, onClose, onChange }: Props) {
  const [docs, setDocs] = useState<CertificationDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [documentType, setDocumentType] = useState("");
  const [uploading, setUploading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDocs(await fetchCertificationDocuments(certification.id));
      setError(null);
    } catch (err) {
      setError(apiErrorMessage(err, "Failed to load documents"));
    } finally {
      setLoading(false);
    }
  }, [certification.id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setActionError(null);
    try {
      await uploadCertificationDocument(certification.id, file, documentType);
      setDocumentType("");
      await load();
      onChange();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Upload failed"));
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(doc: CertificationDocument) {
    if (!confirm(`Delete "${doc.filename ?? `document-${doc.id}`}"?`)) return;
    setDeletingId(doc.id);
    setActionError(null);
    try {
      await deleteCertificationDocument(certification.id, doc.id);
      await load();
      onChange();
    } catch (err) {
      setActionError(apiErrorMessage(err, "Delete failed"));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <Modal isOpen onClose={onClose} className="m-4 max-w-2xl p-6">
      <h2 className="text-lg font-semibold text-[#064273] dark:text-[#e1f2ff]">Documents</h2>
      <p className="mt-1 text-sm text-[#4b738e] dark:text-[#b8dcf2]">{certification.name}</p>

      <div className="mt-4">
        {loading ? (
          <p className="text-sm text-[#5e8198] dark:text-[#b8dcf2]">Loading...</p>
        ) : error ? (
          <p className="text-sm text-rose-600">{error}</p>
        ) : docs.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[#c7dceb] px-4 py-8 text-center text-sm text-[#5e8198] dark:border-[#215777] dark:text-[#b8dcf2]">
            No documents attached.
          </div>
        ) : (
          <ul className="divide-y divide-[#edf4f8] rounded-2xl border border-[#dbe8f1] dark:divide-[#123f5f] dark:border-[#14486a]">
            {docs.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <a
                    href={d.download_url}
                    target="_blank"
                    rel="noreferrer"
                    className="break-all text-sm font-medium text-[#0a5f95] hover:underline dark:text-[#7cc4f2]"
                  >
                    {d.filename ?? `document-${d.id}`}
                  </a>
                  <p className="text-xs text-[#5d7e94] dark:text-[#a9cee5]">
                    {d.document_type ? labelize(d.document_type) : "other"}
                    {d.uploaded_at ? ` · ${new Date(d.uploaded_at).toLocaleDateString()}` : ""}
                  </p>
                </div>
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => void handleDelete(d)}
                    disabled={deletingId === d.id}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-700 transition hover:bg-rose-100 disabled:opacity-60 dark:border-rose-900/40 dark:bg-rose-900/20 dark:text-rose-300"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    {deletingId === d.id ? "Deleting..." : "Delete"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {canEdit && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <input
            className={inputClass}
            list="certification-document-types-upload"
            placeholder="Document type (e.g. certificate, report)"
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value)}
            disabled={uploading}
          />
          <datalist id="certification-document-types-upload">
            <option value="certificate" />
            <option value="report" />
            <option value="report.json for IATF CARA" />
          </datalist>
          <input
            type="file"
            onChange={handleFileSelected}
            disabled={uploading}
            className="block w-full self-center text-sm text-[#0d3550] dark:text-[#e1f2ff]"
          />
        </div>
      )}
      {uploading && <p className="mt-2 text-sm text-[#5e8198] dark:text-[#b8dcf2]">Uploading...</p>}
      {actionError && <p className="mt-2 text-sm text-rose-600">{actionError}</p>}

      <div className="mt-5 flex justify-end">
        <button
          type="button"
          onClick={onClose}
          className="rounded-xl border border-[#9ec6df] px-4 py-2.5 text-sm font-semibold text-[#064273] transition hover:bg-[#f6fbff] dark:border-[#0f6ea9] dark:text-[#e1f2ff]"
        >
          Close
        </button>
      </div>
    </Modal>
  );
}
