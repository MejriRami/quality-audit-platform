import { useDispatch } from "react-redux";
import { deleteAuditType } from "../../redux/auditType/auditType";
import { Shapes, Trash2 } from "lucide-react";

interface AuditType {
  id: string;
  value: string;
}

interface AuditTypeSectionProps {
  auditTypes: AuditType[];
}

const AuditTypeSection = ({ auditTypes }: AuditTypeSectionProps) => {
  const dispatch = useDispatch();

  const handleDeleteAuditType = async (id: string) => {
    deleteAuditType(id, dispatch);
  };

  return (
    <section className="rounded-2xl border border-[#064273]/15 bg-white shadow-sm dark:border-white/10 dark:bg-white/[0.03]">
      <div className="border-b border-[#064273]/10 px-5 py-4 dark:border-white/10">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          Audit Types
        </h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Classification options used when planning questionnaires.
        </p>
      </div>

      {auditTypes.length === 0 ? (
        <div className="p-8 text-center">
          <p className="text-gray-500 dark:text-gray-400">No audit types found.</p>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2.5 p-4">
          {auditTypes.map((auditType) => (
            <div
              key={auditType.id}
              className="group inline-flex items-center gap-2 rounded-lg border border-[#064273]/15 bg-[#064273]/8 px-3 py-2 text-sm font-medium text-[#064273] transition hover:bg-[#064273]/12 dark:border-[#77b7de]/25 dark:bg-[#064273]/30 dark:text-blue-200"
            >
              <Shapes className="h-3.5 w-3.5" />
              <span>{auditType.value}</span>
              <button
                onClick={() => handleDeleteAuditType(auditType.id)}
                className="rounded-md p-1 text-slate-500 transition hover:bg-white hover:text-red-600 dark:text-slate-300 dark:hover:bg-white/10"
                aria-label={`Delete ${auditType.value}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default AuditTypeSection;
