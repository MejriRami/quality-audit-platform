// components/ModernPanel.tsx

import { ReactNode } from "react";

interface ModernPanelProps {
  title: string;
  children: ReactNode;
  className?: string;
}

export default function Panel({
  title,
  children,
  className = "",
}: ModernPanelProps) {
  return (
    <div
      className={`rounded-3xl border border-[#064273]/15 dark:border-white/10
                  bg-white/90 dark:bg-gray-900/80 backdrop-blur-sm 
                  shadow-lg hover:shadow-xl transition-shadow duration-300 p-6 
                  ${className}`}
    >
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold tracking-tight text-gray-800 dark:text-gray-100">
          {title}
        </h2>
        <div className="mt-1 h-1 w-12 rounded-full bg-gradient-to-r from-[#064273] to-[#0a588a]"></div>
      </div>

      {/* Content */}
      <div>{children}</div>
    </div>
  );
}
