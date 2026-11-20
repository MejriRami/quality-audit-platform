import { useState } from "react";
import Input from "../form/input/InputField";
import Label from "../form/Label";
import Panel from "../form/panel";
import FrameworkInitialForm from "../initialForms/FramworkInitialForm";
import Button from "../ui/button/Button";
import { addFramework } from "../../redux/framework/framework";
import { useDispatch } from "react-redux";

interface FrameworkPanelInterface {
  frameworkList: any[];
}

const FrameworkPanel = ({ frameworkList }: FrameworkPanelInterface) => {
  const dispatch = useDispatch();
  const { formFramework, handleInputValue, setFormFramework } =
    FrameworkInitialForm();
  const [errorMsg, setErrorMsg] = useState("");

  const handleAddFramework = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMsg("");

    const clean = formFramework.label.trim();
    if (!clean) {
      setErrorMsg("Label is required");
      return;
    }

    const exists = frameworkList.some(
      (f: any) => f.label.toLowerCase() === clean.toLowerCase(),
    );

    if (exists) {
      setErrorMsg("Framework already exists");
      return;
    }

    const success = await addFramework(formFramework, dispatch);

    if (success) {
      setFormFramework({ label: "", code: "" });
      setErrorMsg("Framework added successfully");
      setTimeout(() => setErrorMsg(""), 3000);
    } else {
      setErrorMsg("Failed to add framework");
    }
  };

  return (
    <Panel
      title="Add Framework"
      className="border-[#064273]/15 bg-gradient-to-br from-[#f3f9ff] via-white to-[#eef6fd] dark:border-white/10 dark:from-[#06263f]/80 dark:via-[#071f33]/70 dark:to-[#041927]/80"
    >
      <form className="space-y-6" onSubmit={handleAddFramework}>
        <div>
          <Label htmlFor="code">Code</Label>
          <Input
            type="text"
            id="code"
            placeholder="ex. ISO"
            value={formFramework.code}
            onChange={handleInputValue}
            name="code"
          />
        </div>
        <div>
          <Label htmlFor="label">Label</Label>
          <Input
            type="text"
            id="label"
            placeholder="ex. International Organization for Standardization"
            value={formFramework.label}
            onChange={handleInputValue}
            name="label"
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
        <Button className="rounded-lg bg-gradient-to-r from-[#064273] to-[#0a588a] px-4 py-2 font-medium text-white transition hover:from-[#05375f] hover:to-[#064273]">
          Add Framework
        </Button>
      </form>
    </Panel>
  );
};

export default FrameworkPanel;
