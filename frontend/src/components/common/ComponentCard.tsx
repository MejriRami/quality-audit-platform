import React from "react";

interface ComponentCardProps {
  title: string;
  children: React.ReactNode;
  className?: string;
  desc?: string;
}

const ComponentCard: React.FC<ComponentCardProps> = ({
  title,
  children,
  className = "",
  desc = "",
}) => {
  return (
    <div
      className={`rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-950/60 ${className}`}
    >
      <div className="px-5 py-4 sm:px-6">
        <h3 className="text-sm font-semibold tracking-[0.01em] text-gray-900 dark:text-gray-100">
          {title}
        </h3>
        {desc ? (
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            {desc}
          </p>
        ) : null}
      </div>

      <div className="border-t border-gray-100 p-4 dark:border-gray-800 sm:p-6">
        <div className="space-y-6">{children}</div>
      </div>
    </div>
  );
};

export default ComponentCard;
