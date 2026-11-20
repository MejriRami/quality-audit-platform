import React from "react";

type BreadcrumbProps = {
  pageTitle: string;
  description?: string;
  kicker?: string;
  actions?: React.ReactNode;
};

const PageBreadcrumb: React.FC<BreadcrumbProps> = ({
  pageTitle,
  description,
  kicker,
  actions,
}) => {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4 border-b border-slate-200/70 pb-4 dark:border-slate-800/70">
      <div className="min-w-0">
        {kicker ? (
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
            {kicker}
          </p>
        ) : null}
        <h1 className="mt-1 truncate font-['Outfit',sans-serif] text-2xl font-semibold tracking-[0.01em] text-slate-900 dark:text-white sm:text-[28px]">
          {pageTitle}
        </h1>
        {description ? (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-400">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {actions}
        </div>
      ) : null}
    </div>
  );
};

export default PageBreadcrumb;
