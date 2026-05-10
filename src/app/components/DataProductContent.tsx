import { useEffect, useMemo, useState } from "react";
import { Plus, Save, Edit, Trash2, ArrowUpDown, ArrowUp, ArrowDown, X, Search, Download, Upload } from "lucide-react";
import { apiDelete, apiGet, apiPatch, apiPost, buildApiUrl, type ProductTypeDto } from "@/lib/api";
import { useUserStorageKeyPrefix } from "@/app/UserStorageContext";
import { useTableColumnWidths } from "@/lib/useTableColumnWidths";
import { useTableRowHeights } from "@/lib/useTableRowHeights";
import { ColumnResizeHandle } from "./ColumnResizeHandle";
import { TableRowResizeHandle } from "./TableRowResizeHandle";
import { ExcelUploadDialog } from "./ExcelUploadDialog";

type SortDirection = "asc" | "desc" | null;
type Field = "code" | "name" | "parentCode" | "level" | "remark";

type ProductRow = {
  code: string;
  name: string;
  parentCode: string;
  level: string;
  remark: string;
  isNew?: boolean;
  tempId?: string;
};

const PRODUCT_CODE_REGEX = /^Z\d{4,8}$/;
const PRODUCT_CODE_HINT = "产品科目代码格式不正确。正确格式：Z + 4~8位数字，例如：Z0001、Z010101、Z02010304。";
const isPkConflict = (msg: string) =>
  msg.includes("已存在") || msg.includes("UNIQUE") || msg.includes("unique");

export function DataProductContent() {
  const uPfx = useUserStorageKeyPrefix();
  const { colStyle, beginColumnResize } = useTableColumnWidths(`${uPfx}::data-product-cols`, {
    minWidth: 56,
    maxWidth: 400,
  });
  const { rowStyle, beginResize } = useTableRowHeights(`${uPfx}::data-product-main`, {
    minHeight: 22,
    maxHeight: 200,
  });
  const [sortColumn, setSortColumn] = useState<keyof ProductRow | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [searchText, setSearchText] = useState("");
  const [rows, setRows] = useState<ProductRow[]>([]);
  const [editingCell, setEditingCell] = useState<{ rowKey: string; field: Field } | null>(null);
  const [showExcelDialog, setShowExcelDialog] = useState(false);
  const [importMode, setImportMode] = useState<"upsert" | "replace">("upsert");

  const validateCode = (code: string) => PRODUCT_CODE_REGEX.test(code);
  const rowKeyOf = (row: ProductRow) => (row.isNew ? row.tempId ?? "" : row.code);
  const inputId = (rowKey: string, field: Field) => `product-input-${rowKey}-${field}`;

  const reload = async () => {
    const products = await apiGet<ProductTypeDto[]>("/api/product-types");
    setRows(
      products.map((p) => ({
        code: p.product_code,
        name: p.product_name,
        parentCode: p.parent_code ?? "",
        level: String(p.level ?? 1),
        remark: p.remark ?? "",
      }))
    );
  };

  useEffect(() => {
    reload().catch((e) => alert(`加载产品科目失败：${e.message}`));
  }, []);

  const sortedFiltered = useMemo(() => {
    let list = rows.filter((row) => {
      const s = searchText.trim().toLowerCase();
      if (!s) return true;
      return row.code.toLowerCase().includes(s) || row.name.toLowerCase().includes(s) || row.parentCode.toLowerCase().includes(s) || row.remark.toLowerCase().includes(s);
    });
    if (sortColumn && sortDirection) {
      list = [...list].sort((a, b) => {
        const va = String(a[sortColumn] ?? "");
        const vb = String(b[sortColumn] ?? "");
        const c = va.localeCompare(vb, "zh-CN");
        return sortDirection === "asc" ? c : -c;
      });
    }
    return list;
  }, [rows, searchText, sortColumn, sortDirection]);

  const handleSort = (column: keyof ProductRow) => {
    if (sortColumn === column) {
      if (sortDirection === "asc") setSortDirection("desc");
      else if (sortDirection === "desc") {
        setSortDirection(null);
        setSortColumn(null);
      }
    } else {
      setSortColumn(column);
      setSortDirection("asc");
    }
  };

  const getSortIcon = (column: keyof ProductRow) => {
    if (sortColumn !== column) return <ArrowUpDown className="w-3 h-3 text-gray-400" />;
    return sortDirection === "asc" ? <ArrowUp className="w-3 h-3 text-blue-600" /> : <ArrowDown className="w-3 h-3 text-blue-600" />;
  };

  const handleAdd = () => {
    if (rows.some((r) => r.isNew)) {
      alert("请先完成当前新增记录的编辑（产品代码和名称）");
      return;
    }
    const tempId = `new-${Date.now()}`;
    setRows([{ code: "", name: "", parentCode: "", level: "1", remark: "", isNew: true, tempId }, ...rows]);
    setTimeout(() => setEditingCell({ rowKey: tempId, field: "code" }), 0);
  };

  const updateRow = (rowKey: string, field: Field, value: string) => {
    setRows((prev) => prev.map((r) => (rowKeyOf(r) === rowKey ? { ...r, [field]: value } : r)));
  };

  const findRow = (rowKey: string) => rows.find((r) => rowKeyOf(r) === rowKey);
  const refocusCell = (rowKey: string, field: Field) => {
    setEditingCell({ rowKey, field });
    setTimeout(() => {
      const el = document.getElementById(inputId(rowKey, field)) as HTMLInputElement | null;
      el?.focus();
      el?.select?.();
    }, 0);
  };

  const persistNewRow = async (row: ProductRow) => {
    const code = row.code.trim();
    const name = row.name.trim();
    if (!code || !name) return;
    if (!validateCode(code)) throw new Error("产品代码格式错误，应为 Z + 4~8 位数字（例如 Z0001、Z010101）");
    await apiPost<ProductTypeDto>("/api/product-types", {
      product_code: code,
      product_name: name,
      parent_code: row.parentCode.trim() || null,
      level: parseInt(row.level, 10) || 1,
      remark: row.remark.trim() || null,
    });
  };

  const patchExistingRow = async (row: ProductRow) => {
    await apiPatch<ProductTypeDto>(`/api/product-types/${row.code}`, {
      product_name: row.name.trim(),
      parent_code: row.parentCode.trim() || null,
      level: parseInt(row.level, 10) || 1,
      remark: row.remark.trim() || null,
    });
  };

  const handleCellBlur = async (rowKey: string, field: Field, value: string) => {
    updateRow(rowKey, field, value);
    const row = findRow(rowKey);
    if (!row) return false;
    const draft = { ...row, [field]: value };
    try {
      if (draft.isNew) {
        if (draft.code.trim() && !validateCode(draft.code.trim())) {
          alert(PRODUCT_CODE_HINT);
          refocusCell(rowKey, "code");
          return false;
        }
        if (draft.code.trim() && draft.name.trim()) {
          await persistNewRow(draft);
          await reload();
        } else {
          setRows((prev) =>
            prev.map((r) => (rowKeyOf(r) === rowKey ? { ...draft } : r))
          );
        }
      } else {
        if (field === "code") {
          alert("产品代码为主键，创建后不可修改");
          await reload();
          refocusCell(rowKey, "name");
          return false;
        }
        if (!draft.name.trim()) {
          alert("产品科目名称不能为空。");
          refocusCell(rowKey, "name");
          return false;
        }
        await patchExistingRow(draft);
        await reload();
      }
      setEditingCell(null);
      return true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "保存失败";
      alert(msg);
      refocusCell(rowKey, isPkConflict(msg) ? "code" : field);
      return false;
    }
  };

  const handleDelete = async (row: ProductRow) => {
    if (row.isNew) {
      setRows((prev) => prev.filter((r) => rowKeyOf(r) !== rowKeyOf(row)));
      return;
    }
    if (!confirm(`确认删除产品科目 ${row.code} 吗？`)) return;
    try {
      await apiDelete(`/api/product-types/${row.code}`);
      await reload();
    } catch (e) {
      alert(e instanceof Error ? e.message : "删除失败");
    }
  };

  const handleSaveRefresh = async () => {
    const pending = rows.filter((r) => r.isNew);
    for (const row of pending) {
      if (!row.code.trim() || !row.name.trim()) {
        alert("仍有新增记录未完成：产品科目代码与名称不能为空。");
        refocusCell(rowKeyOf(row), !row.code.trim() ? "code" : "name");
        return;
      }
      if (!validateCode(row.code.trim())) {
        alert(PRODUCT_CODE_HINT);
        refocusCell(rowKeyOf(row), "code");
        return;
      }
    }
    try {
      for (const row of pending) {
        await persistNewRow(row);
      }
      await reload();
      alert("已从数据库刷新产品科目列表。");
    } catch (e) {
      alert(e instanceof Error ? e.message : "保存失败");
    }
  };

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">产品科目维护</h3>
        <div className="flex-1" />
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索产品..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-48 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          {searchText && (
            <button type="button" onClick={() => setSearchText("")} className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded">
              <X className="w-3 h-3 text-gray-500" />
            </button>
          )}
        </div>
        <button onClick={handleAdd} className="flex items-center gap-1 px-3 py-1 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]">
          <Plus className="w-3 h-3" />
          新增产品
        </button>
        <button onClick={handleSaveRefresh} className="flex items-center gap-1 px-3 py-1 text-xs bg-[#e67e22] text-white rounded hover:bg-[#d35400]">
          <Save className="w-3 h-3" />
          保存并刷新
        </button>
        <button
          onClick={async () => {
            try {
              const resp = await fetch(buildApiUrl("/api/product-types/template"), { credentials: "include" });
              if (!resp.ok) throw new Error("下载失败");
              const blob = await resp.blob();
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = "产品导入模板.xlsx";
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            } catch (e) {
              alert(e instanceof Error ? e.message : "下载模板失败");
            }
          }}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-[#16a085] text-white rounded hover:bg-[#138d75]"
        >
          <Download className="w-3 h-3" />
          下载模板
        </button>
        <button
          onClick={() => setShowExcelDialog(true)}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-[#27ae60] text-white rounded hover:bg-[#229954]"
        >
          <Upload className="w-3 h-3" />
          Excel上传
        </button>
        <button
          onClick={() => setImportMode((m) => (m === "upsert" ? "replace" : "upsert"))}
          className={`flex items-center gap-1 px-3 py-1 text-xs border rounded transition-colors ${
            importMode === "replace"
              ? "bg-red-50 border-red-400 text-red-700"
              : "border-gray-300 text-gray-500 hover:bg-gray-50"
          }`}
          title={importMode === "replace" ? "覆盖模式：导入前先清空全部产品，再写入新数据" : "追加模式：只新增/更新，不删除已有产品"}
        >
          {importMode === "replace" ? "🔄 覆盖模式" : "➕ 追加模式"}
        </button>
      </div>

      <div className="flex-1 border border-gray-300 rounded overflow-auto">
        <table className="text-xs border-collapse" style={{ minWidth: "100%" }}>
          <thead className="bg-gray-100 border-b border-gray-300 sticky top-0">
            <tr>
              <th
                className="relative px-2 py-0.5 pr-2.5 text-left text-gray-700 font-medium border-r border-gray-200"
                style={colStyle("prod-code", 120)}
              >
                <button onClick={() => handleSort("code")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  产品科目代码
                  {getSortIcon("code")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("prod-code", e, 120)} />
              </th>
              <th
                className="relative px-2 py-0.5 pr-2.5 text-left text-gray-700 font-medium border-r border-gray-200"
                style={colStyle("prod-name", 220)}
              >
                <button onClick={() => handleSort("name")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  产品科目名称
                  {getSortIcon("name")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("prod-name", e, 220)} />
              </th>
              <th
                className="relative px-2 py-0.5 pr-2.5 text-left text-gray-700 font-medium border-r border-gray-200"
                style={colStyle("prod-parent", 140)}
              >
                <button onClick={() => handleSort("parentCode")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  父级代码
                  {getSortIcon("parentCode")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("prod-parent", e, 140)} />
              </th>
              <th
                className="relative px-2 py-0.5 pr-2.5 text-center text-gray-700 font-medium border-r border-gray-200"
                style={colStyle("prod-level", 60)}
              >
                <button onClick={() => handleSort("level")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  层级
                  {getSortIcon("level")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("prod-level", e, 60)} />
              </th>
              <th
                className="relative px-2 py-0.5 pr-2.5 text-center text-gray-700 font-medium border-r border-gray-200"
                style={colStyle("prod-actions", 80)}
              >
                操作
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("prod-actions", e, 80)} />
              </th>
              <th
                className="relative px-2 py-0.5 pr-2.5 text-left text-gray-700 font-medium"
                style={colStyle("prod-remark", 160)}
              >
                <button onClick={() => handleSort("remark")} className="flex items-center gap-1 hover:text-blue-600 transition-colors">
                  备注
                  {getSortIcon("remark")}
                </button>
                <ColumnResizeHandle onResizeStart={(e) => beginColumnResize("prod-remark", e, 160)} />
              </th>
            </tr>
          </thead>
          <tbody className="bg-white">
            {sortedFiltered.map((row) => {
              const rowKey = rowKeyOf(row);
              return (
                <tr
                  key={rowKey}
                  style={rowStyle(rowKey)}
                  className={`border-b border-gray-200 ${row.isNew ? "bg-yellow-50" : "hover:bg-gray-50"}`}
                >
                  <td className="relative px-2 py-0.5 pb-1.5 border-r border-gray-200" style={colStyle("prod-code", 120)}>
                    {editingCell?.rowKey === rowKey && editingCell.field === "code" ? (
                      <input
                        type="text"
                        id={inputId(rowKey, "code")}
                        value={row.code}
                        onChange={(e) => updateRow(rowKey, "code", e.target.value)}
                        onBlur={(e) => void handleCellBlur(rowKey, "code", e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === "Tab") {
                            e.preventDefault();
                            void handleCellBlur(rowKey, "code", e.currentTarget.value).then((ok) => {
                              if (ok) setEditingCell({ rowKey, field: "name" });
                            });
                          }
                        }}
                        autoFocus
                        className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
                      />
                    ) : (
                      <div role="button" tabIndex={0} onClick={() => row.isNew && setEditingCell({ rowKey, field: "code" })} className="cursor-text font-mono text-gray-700 hover:bg-blue-50 px-1 rounded min-h-[18px] w-full">
                        {row.code || <span className="text-gray-400">点击输入产品代码</span>}
                      </div>
                    )}
                    <TableRowResizeHandle onResizeStart={(e) => beginResize(rowKey, e)} />
                  </td>
                  <td className="px-2 py-0.5 border-r border-gray-200" style={colStyle("prod-name", 220)}>
                    {editingCell?.rowKey === rowKey && editingCell.field === "name" ? (
                      <input
                        type="text"
                        id={inputId(rowKey, "name")}
                        value={row.name}
                        onChange={(e) => updateRow(rowKey, "name", e.target.value)}
                        onBlur={(e) => void handleCellBlur(rowKey, "name", e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void handleCellBlur(rowKey, "name", e.currentTarget.value);
                          }
                        }}
                        autoFocus
                        className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                      />
                    ) : (
                      <div role="button" tabIndex={0} onClick={() => setEditingCell({ rowKey, field: "name" })} className="cursor-text text-gray-700 hover:bg-blue-50 px-1 rounded min-h-[18px] w-full">
                        {row.name || <span className="text-gray-400">点击输入产品名称</span>}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-0.5 border-r border-gray-200" style={colStyle("prod-parent", 140)}>
                    {editingCell?.rowKey === rowKey && editingCell.field === "parentCode" ? (
                      <input
                        type="text"
                        id={inputId(rowKey, "parentCode")}
                        value={row.parentCode}
                        onChange={(e) => updateRow(rowKey, "parentCode", e.target.value)}
                        onBlur={(e) => void handleCellBlur(rowKey, "parentCode", e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void handleCellBlur(rowKey, "parentCode", e.currentTarget.value);
                          }
                        }}
                        autoFocus
                        className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
                      />
                    ) : (
                      <div role="button" tabIndex={0} onClick={() => setEditingCell({ rowKey, field: "parentCode" })} className="cursor-text font-mono text-gray-600 hover:bg-blue-50 px-1 rounded min-h-[18px] w-full">
                        {row.parentCode || <span className="text-gray-400">-</span>}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-0.5 text-center border-r border-gray-200" style={colStyle("prod-level", 60)}>
                    {editingCell?.rowKey === rowKey && editingCell.field === "level" ? (
                      <input
                        type="text"
                        id={inputId(rowKey, "level")}
                        value={row.level}
                        onChange={(e) => updateRow(rowKey, "level", e.target.value)}
                        onBlur={(e) => void handleCellBlur(rowKey, "level", e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void handleCellBlur(rowKey, "level", e.currentTarget.value);
                          }
                        }}
                        autoFocus
                        className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded text-center"
                      />
                    ) : (
                      <div role="button" tabIndex={0} onClick={() => setEditingCell({ rowKey, field: "level" })} className="cursor-text text-gray-600 hover:bg-blue-50 px-1 rounded min-h-[18px] w-full text-center">
                        {row.level || "1"}
                      </div>
                    )}
                  </td>
                  <td className="px-2 py-0.5 text-center border-r border-gray-200" style={colStyle("prod-actions", 80)}>
                    <div className="flex items-center justify-center gap-1">
                      <button type="button" onClick={() => setEditingCell({ rowKey, field: row.isNew ? "code" : "name" })} className="p-1 hover:bg-gray-200 rounded" title="编辑">
                        <Edit className="w-3 h-3 text-gray-600" />
                      </button>
                      <button type="button" onClick={() => void handleDelete(row)} className="p-1 hover:bg-gray-200 rounded" title="删除">
                        <Trash2 className="w-3 h-3 text-gray-600" />
                      </button>
                    </div>
                  </td>
                  <td className="px-2 py-0.5" style={colStyle("prod-remark", 200)}>
                    {editingCell?.rowKey === rowKey && editingCell.field === "remark" ? (
                      <input
                        type="text"
                        id={inputId(rowKey, "remark")}
                        value={row.remark}
                        onChange={(e) => updateRow(rowKey, "remark", e.target.value)}
                        onBlur={(e) => void handleCellBlur(rowKey, "remark", e.target.value)}
                        autoFocus
                        className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                      />
                    ) : (
                      <div role="button" tabIndex={0} onClick={() => setEditingCell({ rowKey, field: "remark" })} className="cursor-text text-gray-600 hover:bg-blue-50 px-1 rounded min-w-[100px]">
                        {row.remark || "-"}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ExcelUploadDialog
        isOpen={showExcelDialog}
        onClose={() => setShowExcelDialog(false)}
        title="产品导入"
        fields={[
          { key: "product_code", label: "产品科目代码", required: true },
          { key: "product_name", label: "产品科目名称", required: true },
          { key: "parent_code", label: "父级产品代码", required: false },
          { key: "level", label: "层级", required: false },
          { key: "remark", label: "备注", required: false },
        ]}
        templateName="product_type_temp"
        previewEndpoint="/api/product-types/import-preview"
        importEndpoint="/api/product-types/import-apply"
        importMode={importMode}
        onImportComplete={() => void reload()}
      />
    </div>
  );
}
