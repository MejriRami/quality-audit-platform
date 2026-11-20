import { useEffect } from "react";
import PageMeta from "../../components/common/PageMeta";
import PageBreadcrumb from "../../components/common/PageBreadCrumb";
import { useDispatch, useSelector } from "react-redux";
import { getAuditTypes } from "../../redux/auditType/auditType";
import AuditTypeSection from "../../components/framework/AuditTypeSection";
import AuditTypePanel from "../../components/framework/AuditTypePanel";
import FrameworkSection from "../../components/framework/FrameworkSection";
import { getFrameworks } from "../../redux/framework/framework";
import FrameworkPanel from "../../components/framework/FrameworkPanel";
import { Layers, Shapes } from "lucide-react";

export default function FrameworkElements() {
  const dispatch = useDispatch();
  const { auditTypesList } = useSelector((state: any) => state.auditType);
  const { frameworksList } = useSelector((state: any) => state.framework);

  useEffect(() => {
    getAuditTypes(dispatch);
    getFrameworks(dispatch);
  }, [dispatch]);

  return (
    <div className="space-y-6">
      <PageMeta title="Framework Management" description="" />
      <PageBreadcrumb
        kicker="Governance"
        pageTitle="Framework Configuration"
        description="Maintain frameworks and audit types in one consistent workspace."
        actions={
          <>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200/70 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm dark:border-slate-800/70 dark:bg-slate-950/60 dark:text-slate-100">
              <Layers className="h-3.5 w-3.5" />
              {frameworksList?.length ?? 0} Frameworks
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200/70 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm dark:border-slate-800/70 dark:bg-slate-950/60 dark:text-slate-100">
              <Shapes className="h-3.5 w-3.5" />
              {auditTypesList?.length ?? 0} Audit Types
            </span>
          </>
        }
      />

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <FrameworkSection frameworks={frameworksList} />
        <AuditTypeSection auditTypes={auditTypesList} />
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <FrameworkPanel frameworkList={frameworksList} />
        <AuditTypePanel auditTypes={auditTypesList} />
      </section>
    </div>
  );
}
