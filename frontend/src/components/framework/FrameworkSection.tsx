import { useState } from "react";
import { Framework } from "../../redux/framework/framework-slice-types";
import { Modal } from "../ui/modal";
import ConfirmDialog from "../form/ConfirmDialogProps";
import FrameworkInitialForm from "../initialForms/FramworkInitialForm";
import Label from "../form/Label";
import Input from "../form/input/InputField";
import Button from "../ui/button/Button";
import {
  deleteFramework,
  updateFramework,
} from "../../redux/framework/framework";
import { useDispatch } from "react-redux";
import { toast } from "react-hot-toast";
import { Pencil, Trash2 } from "lucide-react";

interface FrameworkSectionProps {
  frameworks: Framework[];
}

const FrameworkSection = ({ frameworks }: FrameworkSectionProps) => {
  const dispatch = useDispatch();
  const [selectedFramework, setSelectedFramework] = useState<any>(null);
  const { formFramework, handleInputValue, setFormFramework } =
    FrameworkInitialForm();
  const [isOpen, setIsOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);

  const handleEdit = (framework: Framework) => {
    setSelectedFramework(framework);
    setIsOpen(true);
    setFormFramework(framework);
  };

  const openDeleteConfirm = (framework: Framework) => {
    setSelectedFramework(framework);
    setIsConfirmOpen(true);
  };

  const closeModal = () => {
    setSelectedFramework(null);
    setIsOpen(false);
  };

  const handleEditSubmit =
    (frameworkValues: any) => (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      updateFramework(selectedFramework.id, frameworkValues, dispatch);
      closeModal();
      toast.success("Framework updated successfully");
    };

  const handleConfirmDelete = () => {
    deleteFramework(selectedFramework.id, dispatch);
    setIsConfirmOpen(false);
  };

  return (
    <>
      <section className="rounded-2xl border border-[#064273]/15 bg-white shadow-sm dark:border-white/10 dark:bg-white/[0.03]">
        <div className="border-b border-[#064273]/10 px-5 py-4 dark:border-white/10">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Frameworks
          </h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Reusable standards with stable code labels.
          </p>
        </div>

        {frameworks.length === 0 && (
          <div className="p-8 text-center">
            <p className="text-gray-500 dark:text-gray-400">
              No frameworks found.
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2">
          {frameworks.map((f) => (
            <div
              key={f.id}
              className="rounded-xl border border-[#064273]/15 bg-gradient-to-br from-white to-slate-50/70 p-4 shadow-sm transition hover:shadow-md dark:border-white/10 dark:from-white/[0.04] dark:to-white/[0.02]"
            >
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {f.label}
                </h3>
                <span className="inline-flex rounded-full border border-[#064273]/20 bg-[#064273]/10 px-2.5 py-1 text-xs font-medium text-[#064273] dark:border-[#77b7de]/30 dark:bg-[#064273]/35 dark:text-blue-200">
                  {f.code}
                </span>
              </div>

              <div className="mt-4 flex items-center gap-2">
                <button
                  onClick={() => handleEdit(f)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[#064273]/20 bg-[#064273]/10 px-3 py-1.5 text-xs font-semibold text-[#064273] transition hover:bg-[#064273]/15 dark:border-[#77b7de]/30 dark:bg-[#064273]/30 dark:text-blue-200"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </button>

                <button
                  onClick={() => openDeleteConfirm(f)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-orange-200 bg-orange-50 px-3 py-1.5 text-xs font-semibold text-orange-700 transition hover:bg-orange-100 dark:border-orange-800/40 dark:bg-orange-900/20 dark:text-orange-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <Modal
        isOpen={isOpen && selectedFramework !== null}
        onClose={closeModal}
        className="max-w-[700px] p-6 lg:p-10"
      >
        <form
          className="custom-scrollbar flex flex-col overflow-y-auto px-2"
          onSubmit={handleEditSubmit(formFramework)}
        >
          <div>
            <h5 className="modal-title mb-2 text-theme-xl font-semibold text-gray-800 dark:text-white/90 lg:text-2xl">
              Edit Framework
            </h5>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Modify the details of the selected framework.
            </p>
          </div>

          <div className="mt-8 space-y-6">
            <div>
              <Label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-400">
                Label
              </Label>
              <Input
                type="text"
                value={formFramework?.label || ""}
                onChange={handleInputValue}
                className="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                name="label"
              />
            </div>

            <div>
              <Label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-400">
                Code
              </Label>
              <input
                type="text"
                value={formFramework?.code || ""}
                onChange={handleInputValue}
                className="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                name="code"
              />
            </div>
          </div>

          <div className="mt-6 flex items-center gap-3 sm:justify-end">
            <button
              onClick={closeModal}
              type="button"
              className="rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400"
            >
              Close
            </button>
            <Button className="rounded-lg bg-gradient-to-r from-[#064273] to-[#0a588a] px-4 py-2 text-white hover:from-[#05375f] hover:to-[#064273]">
              Update Framework
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        isOpen={isConfirmOpen}
        title="Delete Framework"
        message="Are you sure you want to delete this Framework? This action cannot be undone."
        confirmText="Delete"
        cancelText="Cancel"
        onConfirm={handleConfirmDelete}
        onCancel={() => setIsConfirmOpen(false)}
      />
    </>
  );
};

export default FrameworkSection;
