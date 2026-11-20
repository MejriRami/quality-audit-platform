import React from "react";
import {
  XMarkIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";
import { motion, AnimatePresence } from "framer-motion";

interface ReasonModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (reason: string) => void;
}

export const ReasonModal: React.FC<ReasonModalProps> = ({
  open,
  onClose,
  onSubmit,
}) => {
  const [text, setText] = React.useState("");
  const [touched, setTouched] = React.useState(false);

  const isEmpty = text.trim().length === 0;
  const showError = touched && isEmpty;

  const handleSubmit = () => {
    setTouched(true);
    if (isEmpty) return;
    onSubmit(text.trim());
    setText("");
    setTouched(false);
  };

  const handleClose = () => {
    setText("");
    setTouched(false);
    onClose();
  };

  // Close on Escape
  React.useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[99999] flex items-center justify-center p-4">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute inset-0 bg-gray-900/50 backdrop-blur-[3px]"
            onClick={handleClose}
          />

          {/* Dialog */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-[#064273]/15 bg-white shadow-2xl dark:border-[#064273]/40 dark:bg-gray-900"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Top accent bar */}
            <div className="h-1 w-full bg-gradient-to-r from-[#064273] via-[#0a4f7f] to-[#F68C1F]" />

            {/* Header */}
            <div className="flex items-start justify-between px-6 pt-5 pb-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-rose-100 dark:bg-rose-900/40">
                  <ExclamationTriangleIcon className="h-5 w-5 text-rose-600 dark:text-rose-400" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                    Reject Corrective Action
                  </h2>
                  <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                    This will notify the auditee with your reason.
                  </p>
                </div>
              </div>

              <button
                onClick={handleClose}
                className="ml-4 rounded-lg p-1.5 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-white/10 dark:hover:text-gray-300"
                aria-label="Close"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>

            {/* Body */}
            <div className="px-6 pb-2">
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-gray-500 dark:text-gray-400">
                Rejection reason <span className="text-rose-500">*</span>
              </label>
              <textarea
                autoFocus
                rows={4}
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  setTouched(true);
                }}
                placeholder="Describe why this corrective action is being rejected…"
                className={`w-full resize-none rounded-xl border px-3.5 py-2.5 text-sm text-gray-800 outline-none transition placeholder:text-gray-400 focus:ring-2 dark:bg-white/5 dark:text-gray-200 dark:placeholder:text-gray-500 ${
                  showError
                    ? "border-rose-300 focus:border-rose-400 focus:ring-rose-400/20 dark:border-rose-700"
                    : "border-gray-200 focus:border-[#064273] focus:ring-[#064273]/20 dark:border-white/10"
                }`}
              />
              <div className="mt-1.5 flex items-center justify-between">
                {showError ? (
                  <p className="text-xs text-rose-500">
                    A reason is required before rejecting.
                  </p>
                ) : (
                  <span />
                )}
                <p className="text-xs text-gray-400">
                  {text.trim().length} chars
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-2 px-6 py-4">
              <button
                onClick={handleClose}
                className="rounded-xl border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-600 transition hover:bg-gray-50 dark:border-white/10 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={isEmpty}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#F68C1F] to-[#EF7807] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:brightness-105 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <ExclamationTriangleIcon className="h-4 w-4" />
                Confirm Rejection
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
