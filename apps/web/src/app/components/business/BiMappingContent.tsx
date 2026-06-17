import { useState } from "react";
import { BiAiSubjectMappingTab } from "./BiAiSubjectMappingTab";
import { ManageDeptOwnerMappingTab } from "./ManageDeptOwnerMappingTab";

export function BiMappingContent() {
  const [activeTab, setActiveTab] = useState<"bi-ai-subject" | "manage-dept">("bi-ai-subject");

  return (
    <div className="space-y-4 p-4">
      <h2 className="text-lg font-semibold text-gray-800">BI映射维护</h2>
      <div className="flex border-b border-gray-200">
        <button
          className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "bi-ai-subject" ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setActiveTab("bi-ai-subject")}
        >
          BI-AI科目映射表
        </button>
        <button
          className={`border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "manage-dept" ? "border-blue-600 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
          onClick={() => setActiveTab("manage-dept")}
        >
          BI部门维护
        </button>
      </div>
      {activeTab === "bi-ai-subject" ? (
        <BiAiSubjectMappingTab />
      ) : (
        <ManageDeptOwnerMappingTab />
      )}
    </div>
  );
}
