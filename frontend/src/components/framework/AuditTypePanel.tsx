import Label from "../form/Label";
import Panel from "../form/panel";
import Input from "../form/input/InputField";
import { useState } from "react";
import AuditTypeInitialForm from "../initialForms/AuditTypeInitialForm";
import { addAuditTypes } from "../../redux/auditType/auditType";
import { useDispatch } from "react-redux";
import Button from "../ui/button/Button";

interface AuditType {
  id: string;
  value: string;
}

interface AuditTypePanelProps {
  auditTypes: AuditType[];
}

const AuditTypePanel = ({ auditTypes }: AuditTypePanelProps) => {
  const dispatch = useDispatch();
  const [errorMsg, setErrorMsg] = useState<string>("");
  const { handleInputValue, auditTypeForm, setAuditTypeForm } =
    AuditTypeInitialForm();

  const handleAddAuditType = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg("");

    const clean = auditTypeForm.value.trim();
    if (!clean) {
      setErrorMsg("Audit type is required");
      return;
    }

    const exists = auditTypes.some(
      (t) => t.value.toLowerCase() === clean.toLowerCase(),
    );

    if (exists) {
      setErrorMsg("This audit type already exists");
      return;
    }

    const successful = await addAuditTypes(auditTypeForm, dispatch);

    if (successful) {
      setAuditTypeForm({ value: "" });
      setErrorMsg("Audit type added successfully");
      setTimeout(() => setErrorMsg(""), 3000);
    } else {
      setErrorMsg("Failed to add audit type");
    }
  };

  return (
    <Panel
      title="Add Audit Type"
      className="border-[#064273]/15 bg-gradient-to-br from-[#f3f9ff] via-white to-[#eef6fd] dark:border-white/10 dark:from-[#06263f]/80 dark:via-[#071f33]/70 dark:to-[#041927]/80"
    >
      <form className="space-y-6" onSubmit={handleAddAuditType}>
        <div className="space-y-2">
          <Label htmlFor="value">Audit Type</Label>
          <Input
            type="text"
            id="value"
            placeholder="e.g. Process / System / Product"
            value={auditTypeForm.value}
            onChange={handleInputValue}
            className="w-full"
            name="value"
            required
          />
        </div>
        {errorMsg && (
          <p
            className={`text-sm font-medium ${
              errorMsg.includes("successfully")
                ? "text-emerald-600"
                : "text-red-600"
            }`}
          >
            {errorMsg}
          </p>
        )}
        <Button className="w-full rounded-lg bg-gradient-to-r from-[#064273] to-[#0a588a] py-2.5 font-semibold text-white transition hover:from-[#05375f] hover:to-[#064273]">
          Add Audit Type
        </Button>
      </form>
    </Panel>
  );
};

export default AuditTypePanel;
