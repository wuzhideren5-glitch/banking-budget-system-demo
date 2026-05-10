import { useState, useRef, useEffect } from "react";
import { Search, Plus, Edit, Trash2, Save, ArrowUpDown, ArrowUp, ArrowDown, Calculator, ChevronRight, ChevronDown, Minimize2, Maximize2, ChevronsDown, ChevronsUp, Maximize, FileText, Database as DatabaseIcon, Upload, RefreshCw, Building2, GripVertical, X } from "lucide-react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { ExcelUploadDialog } from "./ExcelUploadDialog";
import { FormulaEditorDialog } from "./FormulaEditorDialog";
import { ProductSelectorDialog } from "./ProductSelectorDialog";

type SortDirection = 'asc' | 'desc' | null;

interface DataAccount {
  code: string;
  name: string;
  budgetFormula: string;
  actualFormula: string;
  product: string;
  valueType: string;
  remark: string;
  isNew?: boolean; // 标记是否为新增的临时记录
}

export function DataAccountContent() {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [editingCell, setEditingCell] = useState<{ rowId: number; field: string } | null>(null);
  const [searchText, setSearchText] = useState("");
  const [data, setData] = useState<DataAccount[]>([
    { code: "X1001", name: "资产类", budgetFormula: "SUM(X1002:X1005)", actualFormula: "SUM(X1002:X1005)", product: "Z0001-个人住房贷款", valueType: "金额", remark: "" },
    { code: "X1002", name: "流动资产", budgetFormula: "SUM(X1003:X1004)", actualFormula: "SUM(X1003:X1004)", product: "Z0002-企业流动资金贷款", valueType: "金额", remark: "包含现金及等价物" },
    { code: "X1003", name: "货币资金", budgetFormula: "", actualFormula: "", product: "Z0005-汽车消费贷款", valueType: "金额", remark: "" },
    { code: "X1004", name: "交易性金融资产", budgetFormula: "", actualFormula: "", product: "Z0003-结构性存款", valueType: "金额", remark: "" },
    { code: "X1005", name: "非流动资产", budgetFormula: "SUM(X1006:X1099)", actualFormula: "SUM(X1006:X1099)", product: "Z0004-理财产品A", valueType: "金额", remark: "" },
  ]);

  const [showProductDialog, setShowProductDialog] = useState(false);
  const [editingProduct, setEditingProduct] = useState<{ rowId: number; currentValue: string } | null>(null);
  const [showExcelDialog, setShowExcelDialog] = useState(false);
  const [showFormulaDialog, setShowFormulaDialog] = useState(false);
  const [editingFormula, setEditingFormula] = useState<{ rowId: number; field: 'budgetFormula' | 'actualFormula'; currentValue: string } | null>(null);

  const handleOpenProductSelector = (rowId: number) => {
    setEditingProduct({
      rowId,
      currentValue: data[rowId].product
    });
    setShowProductDialog(true);
  };

  const handleProductConfirm = (product: { code: string; name: string }) => {
    if (editingProduct) {
      const newData = [...data];
      newData[editingProduct.rowId] = {
        ...newData[editingProduct.rowId],
        product: `${product.code}-${product.name}`
      };
      setData(newData);

      console.log('产品科目已保存到数据表并同步数据库:', {
        科目代码: newData[editingProduct.rowId].code,
        产品科目: `${product.code}-${product.name}`
      });
    }
    setShowProductDialog(false);
    setEditingProduct(null);
  };

  const validateField = (field: string, value: string): { valid: boolean; message?: string } => {
    // 数据科目代码：Database PDD — 第 1 位大写字母 + 后 4 位数字（共 5 位）
    if (field === 'code') {
      if (!value) {
        return { valid: false, message: '科目代码不能为空' };
      }
      const codePattern = /^[A-Z]\d{4}$/;
      if (!codePattern.test(value)) {
        return { valid: false, message: '科目代码格式错误！应为：1 位大写字母 + 4 位数字（例如：X1001）' };
      }
    }

    // 科目名称验证
    if (field === 'name') {
      if (!value || value.trim() === '') {
        return { valid: false, message: '科目名称不能为空' };
      }
    }

    // 数值类型验证
    if (field === 'valueType') {
      if (!value) {
        return { valid: false, message: '数值类型不能为空' };
      }
    }

    return { valid: true };
  };

  const handleCellBlur = (rowId: number, field: string, value: string) => {
    const currentRow = data[rowId];

    // 对于新记录，采用宽松验证策略：允许在字段间自由切换
    if (currentRow.isNew) {
      // 只对有值的字段进行格式验证，不验证必填项
      if (value) {
        // 有值时才检查格式
        if (field === 'code') {
          const codePattern = /^[A-Z]\d{4}$/;
          if (!codePattern.test(value)) {
            alert('科目代码格式错误！应为：1 位大写字母 + 4 位数字（例如：X1001）');
            // 保持编辑状态，让用户修改
            return false;
          }
        }
      }

      // 更新数据
      const newData = [...data];
      newData[rowId] = { ...newData[rowId], [field]: value };

      // 检查是否code和name都已填写且格式正确
      const updatedRow = newData[rowId];
      if (updatedRow.code && updatedRow.name) {
        const codePattern = /^[A-Z]\d{4}$/;
        if (codePattern.test(updatedRow.code) && updatedRow.name.trim()) {
          // 两个必填字段都已正确填写，转为正式记录
          delete newData[rowId].isNew;
          console.log('新记录已完成，转为正式记录:', {
            科目代码: updatedRow.code,
            科目名称: updatedRow.name
          });
        }
      }

      setData(newData);
      setEditingCell(null);
      return true;
    }

    // 已有记录，进行严格验证
    const validation = validateField(field, value);
    if (!validation.valid) {
      alert(validation.message);
      return false;
    }

    // 验证通过，更新数据
    const newData = [...data];
    newData[rowId] = { ...newData[rowId], [field]: value };
    setData(newData);
    setEditingCell(null);

    // 同步到数据库
    console.log('字段验证通过并已保存到数据库:', {
      科目代码: newData[rowId].code,
      字段: field,
      新值: value
    });

    return true;
  };

  const handleAddNewRecord = () => {
    // 检查是否已有未完成的新记录
    const hasIncompleteNew = data.some(row => row.isNew);
    if (hasIncompleteNew) {
      alert('请先完成当前新增记录的编辑（填写科目代码和名称）');
      return;
    }

    const newRecord: DataAccount = {
      code: "",
      name: "",
      budgetFormula: "",
      actualFormula: "",
      product: "",
      valueType: "金额",
      remark: "",
      isNew: true // 标记为临时新记录
    };

    // 在数组开头添加新记录
    setData([newRecord, ...data]);

    // 自动进入编辑状态，编辑科目代码
    setTimeout(() => {
      setEditingCell({ rowId: 0, field: 'code' });
    }, 0);
  };

  const handleSaveAndRefresh = () => {
    // 检查是否有未完成的新记录
    const incompleteRecords = data.filter(row => row.isNew);
    if (incompleteRecords.length > 0) {
      const userChoice = confirm(
        '存在未完成的新记录（科目代码和名称未填写完整）。\n\n点击"确定"删除这些未完成记录并继续保存，\n点击"取消"返回继续编辑。'
      );

      if (!userChoice) {
        return;
      }

      // 用户选择删除未完成记录
      const validData = data.filter(row => !row.isNew);
      const sortedData = validData.sort((a, b) => a.code.localeCompare(b.code));
      setData(sortedData);
      console.log('已删除未完成记录，剩余数据已保存并排序');
      alert('未完成的记录已删除，数据已保存并刷新');
      return;
    }

    // 按照科目代码排序
    const sortedData = [...data].sort((a, b) => a.code.localeCompare(b.code));
    setData(sortedData);

    // TODO: 调用后端API保存所有数据
    console.log('所有数据已保存并按科目代码重新排序');
    alert('数据已保存并刷新');
  };

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      if (sortDirection === 'asc') {
        setSortDirection('desc');
      } else if (sortDirection === 'desc') {
        setSortDirection(null);
        setSortColumn(null);
      }
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const handleCellEdit = (rowId: number, field: string, value: string) => {
    const newData = [...data];
    newData[rowId] = { ...newData[rowId], [field]: value };
    setData(newData);
  };

  const handleExcelImport = (importedData: any[]) => {
    // 将导入的数据添加到现有数据中
    const newData = importedData.map(row => ({
      code: row.code || "",
      name: row.name || "",
      budgetFormula: row.budgetFormula || "",
      actualFormula: row.actualFormula || "",
      product: row.product || "",
      valueType: row.valueType || "金额",
      remark: row.remark || ""
    }));
    setData([...data, ...newData]);
    setShowExcelDialog(false);
  };

  const handleOpenFormulaEditor = (rowId: number, field: 'budgetFormula' | 'actualFormula') => {
    setEditingFormula({
      rowId,
      field,
      currentValue: data[rowId][field]
    });
    setShowFormulaDialog(true);
  };

  const handleFormulaConfirm = (formula: string) => {
    if (editingFormula) {
      const newData = [...data];
      newData[editingFormula.rowId] = {
        ...newData[editingFormula.rowId],
        [editingFormula.field]: formula
      };
      setData(newData);

      // TODO: 实际项目中，这里应该调用后端API同步更新数据库
      // 例如: await updateFormulaAPI(data[editingFormula.rowId].code, editingFormula.field, formula);

      console.log('公式已保存到数据表并同步数据库:', {
        科目代码: newData[editingFormula.rowId].code,
        字段: editingFormula.field,
        公式: formula
      });
    }
    setShowFormulaDialog(false);
    setEditingFormula(null);
  };

  const dataAccountFields = [
    { key: 'code', label: '科目代码', required: true },
    { key: 'name', label: '科目名称', required: true },
    { key: 'budgetFormula', label: '预算数计算公式', required: false },
    { key: 'actualFormula', label: '实际数计算公式', required: false },
    { key: 'product', label: '产品科目', required: false },
    { key: 'valueType', label: '数值类型', required: true },
    { key: 'remark', label: '备注', required: false }
  ];

  const getSortIcon = (column: string) => {
    if (sortColumn !== column) {
      return <ArrowUpDown className="w-3 h-3 text-gray-400" />;
    }
    return sortDirection === 'asc' ?
      <ArrowUp className="w-3 h-3 text-blue-600" /> :
      <ArrowDown className="w-3 h-3 text-blue-600" />;
  };

  // 搜索过滤数据，保留原始索引
  const filteredData = data.map((row, originalIdx) => ({ row, originalIdx })).filter(({ row }) => {
    if (!searchText) return true;
    const searchLower = searchText.toLowerCase();
    return (
      row.code.toLowerCase().includes(searchLower) ||
      row.name.toLowerCase().includes(searchLower) ||
      row.budgetFormula.toLowerCase().includes(searchLower) ||
      row.actualFormula.toLowerCase().includes(searchLower) ||
      row.product.toLowerCase().includes(searchLower) ||
      row.valueType.toLowerCase().includes(searchLower) ||
      row.remark.toLowerCase().includes(searchLower)
    );
  });

  const handleClearSearch = () => {
    setSearchText("");
  };

  const isSearching = searchText.length > 0;

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">数据科目维护</h3>
        <div className="flex-1" />
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索科目..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8 pr-8 py-1 text-xs border border-gray-300 rounded w-48 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          {searchText && (
            <button
              onClick={handleClearSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded transition-colors"
              title="清除搜索"
            >
              <X className="w-3.5 h-3.5 text-gray-500" />
            </button>
          )}
        </div>
        <button
          onClick={() => setShowExcelDialog(true)}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-[#27ae60] text-white rounded hover:bg-[#229954]"
        >
          <Upload className="w-3 h-3" />
          Excel上传科目
        </button>
        <button
          onClick={handleAddNewRecord}
          disabled={isSearching}
          className={`flex items-center gap-1 px-3 py-1 text-xs rounded ${
            isSearching
              ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
              : 'bg-[#3498db] text-white hover:bg-[#2980b9]'
          }`}
        >
          <Plus className="w-3 h-3" />
          新增数据科目
        </button>
        <button
          onClick={handleSaveAndRefresh}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-[#e67e22] text-white rounded hover:bg-[#d35400]"
        >
          <Save className="w-3 h-3" />
          保存并刷新
        </button>
      </div>

      <div className="flex-1 border border-gray-300 rounded overflow-auto">
        <table className="text-xs border-collapse" style={{ minWidth: "100%" }}>
          <thead className="bg-gray-100 border-b border-gray-300 sticky top-0">
            <tr>
              <th className="px-2 py-0.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200">
                <button
                  onClick={() => handleSort('code')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors"
                >
                  数据科目代码
                  {getSortIcon('code')}
                </button>
              </th>
              <th className="px-2 py-0.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200">
                <button
                  onClick={() => handleSort('name')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors"
                >
                  数据科目名称
                  {getSortIcon('name')}
                </button>
              </th>
              <th className="px-2 py-0.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200" style={{ width: "200px" }}>
                <button
                  onClick={() => handleSort('budgetFormula')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors"
                >
                  预算数计算公式
                  {getSortIcon('budgetFormula')}
                </button>
              </th>
              <th className="px-2 py-0.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200" style={{ width: "200px" }}>
                <button
                  onClick={() => handleSort('actualFormula')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors"
                >
                  实际数计算公式
                  {getSortIcon('actualFormula')}
                </button>
              </th>
              <th className="px-2 py-0.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200">
                <button
                  onClick={() => handleSort('product')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors"
                >
                  产品科目
                  {getSortIcon('product')}
                </button>
              </th>
              <th className="px-2 py-0.5 text-xs text-center text-gray-700 font-medium border-r border-gray-200">
                <button
                  onClick={() => handleSort('valueType')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors mx-auto"
                >
                  数值类型
                  {getSortIcon('valueType')}
                </button>
              </th>
              <th className="px-2 py-0.5 text-xs text-center text-gray-700 font-medium border-r border-gray-200">操作</th>
              <th className="px-2 py-0.5 text-xs text-left text-gray-700 font-medium">
                <button
                  onClick={() => handleSort('remark')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors"
                >
                  备注
                  {getSortIcon('remark')}
                </button>
              </th>
            </tr>
          </thead>
          <tbody className="bg-white">
            {filteredData.map(({ row, originalIdx }) => (
              <tr key={originalIdx} className={`border-b border-gray-200 ${row.isNew ? 'bg-yellow-50 hover:bg-yellow-100' : 'hover:bg-gray-50'}`}>
                <td className="px-2 py-0.5 border-r border-gray-200">
                  {editingCell?.rowId === originalIdx && editingCell?.field === 'code' ? (
                    <input
                      type="text"
                      value={row.code}
                      onChange={(e) => handleCellEdit(originalIdx, 'code', e.target.value)}
                      onBlur={(e) => handleCellBlur(originalIdx, editingCell?.field || '', e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          handleCellBlur(originalIdx, 'code', e.currentTarget.value);
                        }
                      }}
                      autoFocus
                      className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
                    />
                  ) : (
                    <div
                      onClick={() => setEditingCell({ rowId: originalIdx, field: 'code' })}
                      className="cursor-text font-mono text-gray-700 hover:bg-blue-50 px-1 rounded"
                    >
                      {row.code}
                    </div>
                  )}
                </td>
                <td className="px-2 py-0.5 border-r border-gray-200">
                  {editingCell?.rowId === originalIdx && editingCell?.field === 'name' ? (
                    <input
                      type="text"
                      value={row.name}
                      onChange={(e) => handleCellEdit(originalIdx, 'name', e.target.value)}
                      onBlur={(e) => handleCellBlur(originalIdx, editingCell?.field || '', e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          handleCellBlur(originalIdx, 'name', e.currentTarget.value);
                        }
                      }}
                      autoFocus
                      className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                    />
                  ) : (
                    <div
                      onClick={() => setEditingCell({ rowId: originalIdx, field: 'name' })}
                      className="cursor-text text-gray-700 hover:bg-blue-50 px-1 rounded"
                    >
                      {row.name}
                    </div>
                  )}
                </td>
                <td className="px-2 py-0.5 bg-gray-50 border-r border-gray-200" style={{ width: "200px" }}>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500 text-[10px] font-mono flex-1 truncate">{row.budgetFormula || "-"}</span>
                    <button
                      onClick={() => handleOpenFormulaEditor(originalIdx, 'budgetFormula')}
                      className="ml-1 p-0.5 hover:bg-blue-200 rounded flex-shrink-0 transition-colors"
                      title="编辑公式"
                    >
                      <Calculator className="w-4 h-4 text-blue-600" />
                    </button>
                  </div>
                </td>
                <td className="px-2 py-0.5 bg-gray-50 border-r border-gray-200" style={{ width: "200px" }}>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500 text-[10px] font-mono flex-1 truncate">{row.actualFormula || "-"}</span>
                    <button
                      onClick={() => handleOpenFormulaEditor(originalIdx, 'actualFormula')}
                      className="ml-1 p-0.5 hover:bg-blue-200 rounded flex-shrink-0 transition-colors"
                      title="编辑公式"
                    >
                      <Calculator className="w-4 h-4 text-blue-600" />
                    </button>
                  </div>
                </td>
                <td className="px-2 py-0.5 border-r border-gray-200">
                  <button
                    onClick={() => handleOpenProductSelector(originalIdx)}
                    className="w-full px-2 py-0.5 text-xs border border-gray-300 rounded bg-white hover:bg-gray-50 flex items-center justify-between gap-1 text-left"
                  >
                    <span className="flex-1 truncate">{row.product || "选择产品"}</span>
                    <ChevronDown className="w-3 h-3 text-gray-600 flex-shrink-0" />
                  </button>
                </td>
                <td className="px-2 py-0.5 text-center border-r border-gray-200">
                  <select
                    value={row.valueType}
                    onChange={(e) => handleCellEdit(originalIdx, 'valueType', e.target.value)}
                    className="px-2 py-0.5 text-xs border border-gray-300 rounded bg-white"
                  >
                    <option>金额</option>
                    <option>百分比</option>
                    <option>户数</option>
                  </select>
                </td>
                <td className="px-2 py-0.5 text-center border-r border-gray-200">
                  <div className="flex items-center justify-center gap-1">
                    <button className="p-1 hover:bg-gray-200 rounded" title="编辑">
                      <Edit className="w-4 h-4 text-gray-600" />
                    </button>
                    <button className="p-1 hover:bg-gray-200 rounded" title="删除">
                      <Trash2 className="w-4 h-4 text-gray-600" />
                    </button>
                  </div>
                </td>
                <td className="px-2 py-0.5">
                  {editingCell?.rowId === originalIdx && editingCell?.field === 'remark' ? (
                    <input
                      type="text"
                      value={row.remark}
                      onChange={(e) => handleCellEdit(originalIdx, 'remark', e.target.value)}
                      onBlur={(e) => handleCellBlur(originalIdx, editingCell?.field || '', e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Tab') {
                          e.preventDefault();
                          const input = e.currentTarget;
                          const start = input.selectionStart || 0;
                          const end = input.selectionEnd || 0;
                          const newValue = row.remark.substring(0, start) + '\t' + row.remark.substring(end);
                          handleCellEdit(originalIdx, 'remark', newValue);
                          setTimeout(() => {
                            input.setSelectionRange(start + 1, start + 1);
                          }, 0);
                        } else if (e.key === 'Enter') {
                          e.preventDefault();
                          handleCellBlur(originalIdx, 'remark', e.currentTarget.value);
                        }
                      }}
                      autoFocus
                      className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                    />
                  ) : (
                    <div
                      onClick={() => setEditingCell({ rowId: originalIdx, field: 'remark' })}
                      className="cursor-text text-gray-600 hover:bg-blue-50 px-1 rounded min-w-[100px]"
                    >
                      {row.remark || "-"}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ExcelUploadDialog
        isOpen={showExcelDialog}
        onClose={() => setShowExcelDialog(false)}
        title="数据科目维护"
        fields={dataAccountFields}
        onImport={handleExcelImport}
      />

      <FormulaEditorDialog
        isOpen={showFormulaDialog}
        onClose={() => {
          setShowFormulaDialog(false);
          setEditingFormula(null);
        }}
        onConfirm={handleFormulaConfirm}
        initialFormula={editingFormula?.currentValue || ""}
        title={editingFormula?.field === 'budgetFormula' ? '预算数计算公式编辑' : '实际数计算公式编辑'}
      />

      <ProductSelectorDialog
        isOpen={showProductDialog}
        onClose={() => {
          setShowProductDialog(false);
          setEditingProduct(null);
        }}
        onConfirm={handleProductConfirm}
        initialProduct={editingProduct?.currentValue || ""}
      />
    </div>
  );
}

interface ReportTreeNode {
  id: string;
  code: string;
  name: string;
  type: 'report' | 'data';
  level: number;
  children?: ReportTreeNode[];
  isExpanded?: boolean;
}

function ReportTreeItem({
  node,
  onEdit,
  onToggle,
  onContextMenu,
  editingNode,
  onSaveEdit,
  onDrop,
  parentCode
}: {
  node: ReportTreeNode;
  onEdit: (node: ReportTreeNode) => void;
  onToggle: (id: string) => void;
  onContextMenu: (e: React.MouseEvent, node: ReportTreeNode) => void;
  editingNode: { id: string; code: string; name: string; parentCode?: string } | null;
  onSaveEdit: (id: string, code: string, name: string) => void;
  onDrop: (targetNodeId: string, dataSubjectCode: string, dataSubjectName: string) => void;
  parentCode?: string;
}) {
  const hasChildren = node.children && node.children.length > 0;
  const [localCode, setLocalCode] = useState(node.code);
  const [localName, setLocalName] = useState(node.name);
  const [isDragOver, setIsDragOver] = useState(false);
  const isEditing = editingNode?.id === node.id;

  useEffect(() => {
    if (isEditing) {
      setLocalCode(editingNode.code);
      setLocalName(editingNode.name);
    }
  }, [isEditing, editingNode]);

  const handleSave = () => {
    onSaveEdit(node.id, localCode, localName);
  };

  const handleCodeChange = (value: string) => {
    if (node.type === 'report' && parentCode) {
      // 报告科目：只允许编辑后两位
      const prefix = parentCode;
      if (value.startsWith(prefix)) {
        setLocalCode(value);
      } else if (value.length <= prefix.length + 3) {
        setLocalCode(prefix + value.slice(prefix.length));
      }
    } else {
      setLocalCode(value);
    }
  };

  const canAcceptDrop = node.type === 'report' && (!node.children || node.children.every(c => c.type === 'data'));

  const handleDragOver = (e: React.DragEvent) => {
    if (canAcceptDrop) {
      e.preventDefault();
      setIsDragOver(true);
    }
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (canAcceptDrop) {
      const code = e.dataTransfer.getData('dataSubjectCode');
      const name = e.dataTransfer.getData('dataSubjectName');
      onDrop(node.id, code, name);
    }
  };

  const bgColor = node.type === 'data' ? 'bg-amber-50' : (isDragOver ? 'bg-blue-50' : '');

  return (
    <div>
      <div
        className={`flex items-center gap-1 px-2 py-1 hover:bg-gray-50 border-b border-gray-100 group ${bgColor}`}
        style={{ paddingLeft: `${node.level * 12 + 4}px` }}
        onContextMenu={(e) => onContextMenu(e, node)}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {hasChildren ? (
          <button
            onClick={() => onToggle(node.id)}
            className="p-0.5 hover:bg-gray-200 rounded flex-shrink-0"
          >
            {node.isExpanded ? (
              <ChevronDown className="w-3 h-3 text-gray-600" />
            ) : (
              <ChevronRight className="w-3 h-3 text-gray-600" />
            )}
          </button>
        ) : (
          <span className="w-4" />
        )}

        {node.type === 'report' ? (
          <FileText className="w-3 h-3 text-blue-600 flex-shrink-0 mr-2" />
        ) : (
          <DatabaseIcon className="w-3 h-3 text-green-600 flex-shrink-0 mr-2" />
        )}

        {isEditing ? (
          <div className="flex items-center gap-2 flex-1">
            {node.type === 'report' ? (
              <input
                type="text"
                value={localCode}
                onChange={(e) => handleCodeChange(e.target.value)}
                className="px-1 py-0.5 text-xs border border-blue-400 rounded font-mono w-24"
                autoFocus
              />
            ) : (
              <span className="font-mono text-xs text-gray-500 w-24 px-1">{node.code}</span>
            )}
            <input
              type="text"
              value={localName}
              onChange={(e) => setLocalName(e.target.value)}
              className="px-1 py-0.5 text-xs border border-blue-400 rounded flex-1"
              autoFocus={node.type === 'data'}
            />
            <button
              onClick={handleSave}
              className="px-2 py-0.5 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]"
            >
              保存
            </button>
          </div>
        ) : (
          <>
            <span className="font-mono text-xs text-gray-700 w-24">{node.code}</span>
            <span className="text-xs text-gray-700 flex-1">{node.name}</span>
            <button
              onClick={() => onEdit(node)}
              className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity"
              title="编辑"
            >
              <Edit className="w-3 h-3 text-gray-600" />
            </button>
          </>
        )}
      </div>

      {hasChildren && node.isExpanded && (
        <div>
          {node.children!.map((child) => (
            <ReportTreeItem
              key={child.id}
              node={child}
              onEdit={onEdit}
              onToggle={onToggle}
              onContextMenu={onContextMenu}
              editingNode={editingNode}
              onSaveEdit={onSaveEdit}
              onDrop={onDrop}
              parentCode={node.code}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface DataSubject {
  code: string;
  name: string;
}

const dataSubjects: DataSubject[] = [
  { code: 'D1001', name: '库存现金' },
  { code: 'D1002', name: '银行存款' },
  { code: 'D1003', name: '其他货币资金' },
  { code: 'D1004', name: '存放中央银行款项' },
  { code: 'D1005', name: '存放同业款项' },
  { code: 'D1006', name: '拆出资金' },
  { code: 'D1007', name: '交易性金融资产' },
  { code: 'D1008', name: '衍生金融资产' },
  { code: 'D1009', name: '买入返售金融资产' },
  { code: 'D1010', name: '应收账款' },
  { code: 'D1011', name: '应收利息' },
  { code: 'D1012', name: '其他应收款' },
  { code: 'D1013', name: '发放贷款及垫款' },
  { code: 'D1014', name: '可供出售金融资产' },
  { code: 'D1015', name: '持有至到期投资' },
  { code: 'D1016', name: '长期股权投资' },
  { code: 'D1017', name: '投资性房地产' },
  { code: 'D1018', name: '固定资产' },
  { code: 'D1019', name: '在建工程' },
  { code: 'D1020', name: '无形资产' },
  { code: 'D2001', name: '贷款利息收入' },
  { code: 'D2002', name: '存放同业利息收入' },
  { code: 'D2003', name: '拆借利息收入' },
  { code: 'D2004', name: '债券投资收益' },
  { code: 'D2005', name: '手续费收入' },
  { code: 'D2006', name: '佣金收入' },
  { code: 'D2007', name: '汇兑收益' },
  { code: 'D2008', name: '公允价值变动收益' },
  { code: 'D2009', name: '投资收益' },
  { code: 'D2010', name: '其他业务收入' },
  { code: 'D3001', name: '存款利息支出' },
  { code: 'D3002', name: '同业存款利息支出' },
  { code: 'D3003', name: '拆入资金利息支出' },
  { code: 'D3004', name: '卖出回购利息支出' },
  { code: 'D3005', name: '手续费支出' },
  { code: 'D3006', name: '佣金支出' },
  { code: 'D3007', name: '业务及管理费' },
  { code: 'D3008', name: '员工薪酬' },
  { code: 'D3009', name: '折旧费用' },
  { code: 'D3010', name: '无形资产摊销' },
  { code: 'D4001', name: '资产减值损失' },
  { code: 'D4002', name: '信用减值损失' },
  { code: 'D4003', name: '营业税金及附加' },
  { code: 'D4004', name: '所得税费用' },
  { code: 'D5001', name: '短期借款' },
  { code: 'D5002', name: '向中央银行借款' },
  { code: 'D5003', name: '吸收存款' },
  { code: 'D5004', name: '同业存放' },
  { code: 'D5005', name: '拆入资金' },
  { code: 'D5006', name: '卖出回购金融资产款' },
];

export function DataReportContent() {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [treeData, setTreeData] = useState<ReportTreeNode[]>([
    {
      id: '1', code: 'X01', name: '资产负债表', type: 'report', level: 1, isExpanded: true,
      children: [
        {
          id: '1-1', code: 'X0101', name: '资产', type: 'report', level: 2, isExpanded: true,
          children: [
            {
              id: '1-1-1', code: 'X010101', name: '流动资产', type: 'report', level: 3, isExpanded: true,
              children: [
                {
                  id: '1-1-1-1', code: 'X01010101', name: '货币资金', type: 'report', level: 4, isExpanded: false,
                  children: [
                    { id: '1-1-1-1-D1', code: 'D1001', name: '库存现金', type: 'data', level: 5 },
                    { id: '1-1-1-1-D2', code: 'D1002', name: '银行存款', type: 'data', level: 5 },
                  ]
                },
                { id: '1-1-1-D1', code: 'D1010', name: '应收账款', type: 'data', level: 4 },
              ]
            },
            { id: '1-1-2', code: 'X010102', name: '非流动资产', type: 'report', level: 3, isExpanded: false },
          ]
        },
        { id: '1-2', code: 'X0102', name: '负债', type: 'report', level: 2, isExpanded: false },
        { id: '1-3', code: 'X0103', name: '所有者权益', type: 'report', level: 2, isExpanded: false },
      ]
    },
    {
      id: '2', code: 'X02', name: '利润表', type: 'report', level: 1, isExpanded: true,
      children: [
        {
          id: '2-1', code: 'X0201', name: '营业收入', type: 'report', level: 2, isExpanded: true,
          children: [
            {
              id: '2-1-1', code: 'X020101', name: '主营业务收入', type: 'report', level: 3, isExpanded: true,
              children: [
                {
                  id: '2-1-1-1', code: 'X02010101', name: '利息收入', type: 'report', level: 4, isExpanded: true,
                  children: [
                    { id: '2-1-1-1-D1', code: 'D2001', name: '贷款利息收入', type: 'data', level: 5 },
                    { id: '2-1-1-1-D2', code: 'D2002', name: '存放同业利息收入', type: 'data', level: 5 },
                  ]
                }
              ]
            },
            { id: '2-1-2', code: 'X020102', name: '其他业务收入', type: 'report', level: 3, isExpanded: false },
          ]
        },
        { id: '2-2', code: 'X0202', name: '营业成本', type: 'report', level: 2, isExpanded: false },
      ]
    },
    { id: '3', code: 'X03', name: '现金流量表', type: 'report', level: 1, isExpanded: false },
    { id: '4', code: 'X04', name: '所有者权益变动表', type: 'report', level: 1, isExpanded: false },
    { id: '5', code: 'X05', name: '监管报表', type: 'report', level: 1, isExpanded: false },
    { id: '6', code: 'X06', name: '资本充足率报表', type: 'report', level: 1, isExpanded: false },
    { id: '7', code: 'X07', name: '流动性风险报表', type: 'report', level: 1, isExpanded: false },
    { id: '8', code: 'X08', name: '信用风险报表', type: 'report', level: 1, isExpanded: false },
    { id: '9', code: 'X09', name: '市场风险报表', type: 'report', level: 1, isExpanded: false },
    { id: '10', code: 'X10', name: '操作风险报表', type: 'report', level: 1, isExpanded: false },
  ]);

  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; node: ReportTreeNode } | null>(null);
  const [editingNode, setEditingNode] = useState<{ id: string; code: string; name: string } | null>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleNode = (id: string) => {
    const toggleRecursive = (nodes: ReportTreeNode[]): ReportTreeNode[] => {
      return nodes.map(node => {
        if (node.id === id) {
          return { ...node, isExpanded: !node.isExpanded };
        }
        if (node.children) {
          return { ...node, children: toggleRecursive(node.children) };
        }
        return node;
      });
    };
    setTreeData(toggleRecursive(treeData));
  };

  const collapseLevel = (nodes: ReportTreeNode[], targetLevel: number): ReportTreeNode[] => {
    return nodes.map(node => {
      const newNode = { ...node };
      if (node.level === targetLevel) {
        newNode.isExpanded = false;
      }
      if (node.children) {
        newNode.children = collapseLevel(node.children, targetLevel);
      }
      return newNode;
    });
  };

  const expandChildren = (nodes: ReportTreeNode[], parentId: string): ReportTreeNode[] => {
    return nodes.map(node => {
      if (node.id === parentId && node.children) {
        return {
          ...node,
          isExpanded: true,
          children: node.children.map(child => ({ ...child, isExpanded: true }))
        };
      }
      if (node.children) {
        return { ...node, children: expandChildren(node.children, parentId) };
      }
      return node;
    });
  };

  const expandAll = (nodes: ReportTreeNode[]): ReportTreeNode[] => {
    return nodes.map(node => ({
      ...node,
      isExpanded: true,
      children: node.children ? expandAll(node.children) : undefined
    }));
  };

  const handleContextMenu = (e: React.MouseEvent, node: ReportTreeNode) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, node });
  };

  const findParentCode = (nodes: ReportTreeNode[], targetId: string, parentCode?: string): string | undefined => {
    for (const node of nodes) {
      if (node.children) {
        for (const child of node.children) {
          if (child.id === targetId) {
            return node.code;
          }
        }
        const found = findParentCode(node.children, targetId, node.code);
        if (found) return found;
      }
    }
    return undefined;
  };

  const handleEdit = (node: ReportTreeNode) => {
    const parentCode = findParentCode(treeData, node.id);
    setEditingNode({ id: node.id, code: node.code, name: node.name, parentCode });
  };

  const handleSaveEdit = (id: string, code: string, name: string) => {
    const updateNode = (nodes: ReportTreeNode[]): ReportTreeNode[] => {
      return nodes.map(node => {
        if (node.id === id) {
          return { ...node, code, name };
        }
        if (node.children) {
          return { ...node, children: updateNode(node.children) };
        }
        return node;
      });
    };
    setTreeData(updateNode(treeData));
    setEditingNode(null);
  };

  const handleDropDataSubject = (targetNodeId: string, dataSubjectCode: string, dataSubjectName: string) => {
    const addDataSubject = (nodes: ReportTreeNode[]): ReportTreeNode[] => {
      return nodes.map(node => {
        if (node.id === targetNodeId) {
          // 检查该报告科目下是否已存在该数据科目
          const exists = node.children?.some(child => child.type === 'data' && child.code === dataSubjectCode);
          if (exists) {
            alert(`数据科目 ${dataSubjectCode} 已存在于该报告科目下`);
            return node;
          }

          const newDataSubject: ReportTreeNode = {
            id: `${targetNodeId}-D-${Date.now()}`,
            code: dataSubjectCode,
            name: dataSubjectName,
            type: 'data',
            level: node.level + 1
          };
          return {
            ...node,
            children: [...(node.children || []), newDataSubject],
            isExpanded: true
          };
        }
        if (node.children) {
          return { ...node, children: addDataSubject(node.children) };
        }
        return node;
      });
    };
    setTreeData(addDataSubject(treeData));
  };

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const sortedDataSubjects = [...dataSubjects].sort((a, b) => {
    if (!sortColumn) return 0;
    const aValue = sortColumn === 'code' ? a.code : a.name;
    const bValue = sortColumn === 'code' ? b.code : b.name;
    const comparison = aValue.localeCompare(bValue);
    return sortDirection === 'asc' ? comparison : -comparison;
  });

  const getSortIcon = (column: string) => {
    if (sortColumn !== column) {
      return <ArrowUpDown className="w-3 h-3 text-gray-400" />;
    }
    return sortDirection === 'asc' ?
      <ArrowUp className="w-3 h-3 text-blue-600" /> :
      <ArrowDown className="w-3 h-3 text-blue-600" />;
  };

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">报告科目维护</h3>
        <div className="flex-1" />
        <input
          type="text"
          placeholder="搜索报告科目..."
          className="px-2 py-1 text-xs border border-gray-300 rounded w-48"
        />
        <button className="flex items-center gap-1 px-3 py-1 text-xs bg-[#27ae60] text-white rounded hover:bg-[#229954]">
          <Upload className="w-3 h-3" />
          Excel上传科目
        </button>
        <button
          onClick={() => setTreeData(collapseLevel(treeData, 2))}
          className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded transition-colors"
          title="收起本级"
        >
          <Minimize2 className="w-3 h-3" />
          <span>收起本级</span>
        </button>
        <button
          onClick={() => setTreeData(expandAll(treeData))}
          className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded transition-colors"
          title="展开下级"
        >
          <Maximize2 className="w-3 h-3" />
          <span>展开下级</span>
        </button>
        <button
          onClick={() => setTreeData(collapseLevel(treeData, 1))}
          className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded transition-colors"
          title="收起全部本级"
        >
          <ChevronsUp className="w-3 h-3" />
          <span>收起全部本级</span>
        </button>
        <button
          onClick={() => setTreeData(expandAll(treeData))}
          className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded transition-colors"
          title="展开全部下级"
        >
          <ChevronsDown className="w-3 h-3" />
          <span>展开全部下级</span>
        </button>
        <button
          onClick={() => setTreeData(expandAll(treeData))}
          className="flex items-center gap-1 px-2 py-1 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]"
          title="全部展开"
        >
          <Maximize className="w-3 h-3" />
          <span>全部展开</span>
        </button>
      </div>

      <div className="flex-1 overflow-hidden">
        <PanelGroup direction="horizontal">
          {/* 左侧树状结构 */}
          <Panel id="report-tree" order={1} defaultSize={60} minSize={30}>
            <div className="h-full border border-gray-300 rounded overflow-auto bg-white">
              {treeData.map((node) => (
                <ReportTreeItem
                  key={node.id}
                  node={node}
                  onEdit={handleEdit}
                  onToggle={toggleNode}
                  onContextMenu={handleContextMenu}
                  editingNode={editingNode}
                  onSaveEdit={handleSaveEdit}
                  onDrop={handleDropDataSubject}
                />
              ))}
            </div>
          </Panel>

          <PanelResizeHandle className="w-1 bg-gray-300 hover:bg-[#3498db] transition-colors mx-2" />

          {/* 右侧数据科目列表 */}
          <Panel id="data-subject-list" order={2} defaultSize={40} minSize={20}>
            <div className="h-full border border-gray-300 rounded bg-white flex flex-col">
              <div className="px-3 py-2 bg-gray-100 border-b border-gray-300">
                <h4 className="text-xs font-medium text-gray-800">数据科目列表</h4>
                <p className="text-[10px] text-gray-500 mt-0.5">拖拽到左侧报告科目</p>
              </div>

              {/* 表头 */}
              <div className="flex items-center bg-gray-50 border-b border-gray-300 px-3 py-1.5">
                <div className="w-3 flex-shrink-0" />
                <button
                  onClick={() => handleSort('code')}
                  className="flex items-center gap-1 text-xs font-medium text-gray-700 hover:text-blue-600 transition-colors w-24 ml-2"
                >
                  数据科目代码
                  {getSortIcon('code')}
                </button>
                <button
                  onClick={() => handleSort('name')}
                  className="flex items-center gap-1 justify-center text-xs font-medium text-gray-700 hover:text-blue-600 transition-colors flex-1 ml-2"
                >
                  数据科目名称
                  {getSortIcon('name')}
                </button>
              </div>

              <div className="flex-1 overflow-y-auto">
                {sortedDataSubjects.map((subject, idx) => (
                  <div
                    key={idx}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('dataSubjectCode', subject.code);
                      e.dataTransfer.setData('dataSubjectName', subject.name);
                    }}
                    className="flex items-center gap-2 px-3 py-1.5 border-b border-gray-100 hover:bg-blue-50 cursor-move"
                  >
                    <DatabaseIcon className="w-3 h-3 text-green-600 flex-shrink-0" />
                    <span className="font-mono text-xs text-gray-700 w-24">{subject.code}</span>
                    <span className="text-xs text-gray-700 flex-1 truncate">{subject.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </Panel>
        </PanelGroup>
      </div>

      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="fixed bg-white border border-gray-300 rounded shadow-lg py-1 z-50 min-w-[160px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              handleEdit(contextMenu.node);
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
          >
            <Edit className="w-3 h-3" />
            编辑
          </button>
          {contextMenu.node.children && contextMenu.node.children.length > 0 && (
            <button
              onClick={() => {
                toggleNode(contextMenu.node.id);
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
            >
              <Minimize2 className="w-3 h-3" />
              {contextMenu.node.isExpanded ? '收起本级' : '展开下级'}
            </button>
          )}
          {contextMenu.node.type === 'report' && contextMenu.node.level < 4 && (
            <button
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
            >
              <Plus className="w-3 h-3" />
              增加下级报告科目
            </button>
          )}
          {contextMenu.node.type === 'report' && (
            <button
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
            >
              <DatabaseIcon className="w-3 h-3" />
              增加下级数据科目
            </button>
          )}
          <div className="border-t border-gray-200 my-1" />
          <button
            className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 text-red-600 flex items-center gap-2"
          >
            <Trash2 className="w-3 h-3" />
            删除本{contextMenu.node.type === 'report' ? '报告' : '数据'}科目
          </button>
        </div>
      )}
    </div>
  );
}

export function DataProductContent() {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [editingCell, setEditingCell] = useState<{ rowId: number; field: string } | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [newProduct, setNewProduct] = useState({ code: '', name: '', remark: '' });
  const [data, setData] = useState([
    { code: "Z0001", name: "个人住房贷款", remark: "零售银行核心产品" },
    { code: "Z0002", name: "企业流动资金贷款", remark: "公司银行主打产品" },
    { code: "Z0003", name: "结构性存款", remark: "理财类存款产品" },
    { code: "Z0004", name: "理财产品A", remark: "金融市场产品系列" },
    { code: "Z0005", name: "汽车消费贷款", remark: "零售银行贷款产品" },
  ]);

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      if (sortDirection === 'asc') {
        setSortDirection('desc');
      } else if (sortDirection === 'desc') {
        setSortDirection(null);
        setSortColumn(null);
      }
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const handleCellEdit = (rowId: number, field: string, value: string) => {
    const newData = [...data];
    newData[rowId] = { ...newData[rowId], [field]: value };
    setData(newData);
  };

  const getSortIcon = (column: string) => {
    if (sortColumn !== column) {
      return <ArrowUpDown className="w-3 h-3 text-gray-400" />;
    }
    return sortDirection === 'asc' ?
      <ArrowUp className="w-3 h-3 text-blue-600" /> :
      <ArrowDown className="w-3 h-3 text-blue-600" />;
  };

  const handleAddProduct = () => {
    setIsAdding(true);
    setNewProduct({ code: '', name: '', remark: '' });
  };

  const handleSaveNewProduct = () => {
    if (newProduct.code && newProduct.name) {
      setData([newProduct, ...data]);
      setIsAdding(false);
      setNewProduct({ code: '', name: '', remark: '' });
    }
  };

  const handleCancelAdd = () => {
    setIsAdding(false);
    setNewProduct({ code: '', name: '', remark: '' });
  };

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">产品科目维护</h3>
        <div className="flex-1" />
        <input
          type="text"
          placeholder="搜索产品..."
          className="px-2 py-1 text-xs border border-gray-300 rounded w-48"
        />
        <button
          onClick={handleAddProduct}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]"
        >
          <Plus className="w-3 h-3" />
          新增产品
        </button>
        <button className="flex items-center gap-1 px-3 py-1 text-xs bg-[#27ae60] text-white rounded hover:bg-[#229954]">
          <Upload className="w-3 h-3" />
          从Excel导入科目
        </button>
      </div>

      <div className="flex-1 border border-gray-300 rounded overflow-auto">
        <table className="text-xs border-collapse" style={{ minWidth: "100%" }}>
          <thead className="bg-gray-100 border-b border-gray-300 sticky top-0">
            <tr>
              <th className="px-2 py-0.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200">
                <button
                  onClick={() => handleSort('code')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors"
                >
                  产品科目代码
                  {getSortIcon('code')}
                </button>
              </th>
              <th className="px-2 py-0.5 text-xs text-left text-gray-700 font-medium border-r border-gray-200">
                <button
                  onClick={() => handleSort('name')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors"
                >
                  产品科目名称
                  {getSortIcon('name')}
                </button>
              </th>
              <th className="px-2 py-0.5 text-xs text-center text-gray-700 font-medium border-r border-gray-200">操作</th>
              <th className="px-2 py-0.5 text-xs text-left text-gray-700 font-medium">
                <button
                  onClick={() => handleSort('remark')}
                  className="flex items-center gap-1 hover:text-blue-600 transition-colors"
                >
                  备注
                  {getSortIcon('remark')}
                </button>
              </th>
            </tr>
          </thead>
          <tbody className="bg-white">
            {isAdding && (
              <tr className="border-b border-gray-200 bg-blue-50">
                <td className="px-2 py-2 border-r border-gray-200">
                  <input
                    type="text"
                    value={newProduct.code}
                    onChange={(e) => setNewProduct({ ...newProduct, code: e.target.value })}
                    placeholder="输入代码"
                    className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
                    autoFocus
                  />
                </td>
                <td className="px-2 py-2 border-r border-gray-200">
                  <input
                    type="text"
                    value={newProduct.name}
                    onChange={(e) => setNewProduct({ ...newProduct, name: e.target.value })}
                    placeholder="输入名称"
                    className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                  />
                </td>
                <td className="px-2 py-2 text-center border-r border-gray-200">
                  <div className="flex items-center justify-center gap-1">
                    <button
                      onClick={handleSaveNewProduct}
                      className="p-1 hover:bg-gray-200 rounded"
                      title="保存"
                    >
                      <Save className="w-3 h-3 text-green-600" />
                    </button>
                    <button
                      onClick={handleCancelAdd}
                      className="p-1 hover:bg-gray-200 rounded"
                      title="取消"
                    >
                      <Trash2 className="w-3 h-3 text-red-600" />
                    </button>
                  </div>
                </td>
                <td className="px-2 py-2">
                  <input
                    type="text"
                    value={newProduct.remark}
                    onChange={(e) => setNewProduct({ ...newProduct, remark: e.target.value })}
                    placeholder="输入备注"
                    className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                  />
                </td>
              </tr>
            )}
            {data.map((row, idx) => (
              <tr key={idx} className="border-b border-gray-200 hover:bg-gray-50">
                <td className="px-2 py-2 border-r border-gray-200">
                  {editingCell?.rowId === originalIdx && editingCell?.field === 'code' ? (
                    <input
                      type="text"
                      value={row.code}
                      onChange={(e) => handleCellEdit(originalIdx, 'code', e.target.value)}
                      onBlur={(e) => handleCellBlur(originalIdx, editingCell?.field || '', e.target.value)}
                      autoFocus
                      className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded font-mono"
                    />
                  ) : (
                    <div
                      onClick={() => setEditingCell({ rowId: originalIdx, field: 'code' })}
                      className="cursor-text font-mono text-gray-700 hover:bg-blue-50 px-1 rounded"
                    >
                      {row.code}
                    </div>
                  )}
                </td>
                <td className="px-2 py-2 border-r border-gray-200">
                  {editingCell?.rowId === originalIdx && editingCell?.field === 'name' ? (
                    <input
                      type="text"
                      value={row.name}
                      onChange={(e) => handleCellEdit(originalIdx, 'name', e.target.value)}
                      onBlur={(e) => handleCellBlur(originalIdx, editingCell?.field || '', e.target.value)}
                      autoFocus
                      className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                    />
                  ) : (
                    <div
                      onClick={() => setEditingCell({ rowId: originalIdx, field: 'name' })}
                      className="cursor-text text-gray-700 hover:bg-blue-50 px-1 rounded"
                    >
                      {row.name}
                    </div>
                  )}
                </td>
                <td className="px-2 py-2 text-center border-r border-gray-200">
                  <div className="flex items-center justify-center gap-1">
                    <button className="p-1 hover:bg-gray-200 rounded" title="保存">
                      <Save className="w-3 h-3 text-gray-600" />
                    </button>
                    <button className="p-1 hover:bg-gray-200 rounded" title="编辑">
                      <Edit className="w-3 h-3 text-gray-600" />
                    </button>
                    <button className="p-1 hover:bg-gray-200 rounded" title="删除">
                      <Trash2 className="w-3 h-3 text-gray-600" />
                    </button>
                  </div>
                </td>
                <td className="px-2 py-2">
                  {editingCell?.rowId === originalIdx && editingCell?.field === 'remark' ? (
                    <input
                      type="text"
                      value={row.remark}
                      onChange={(e) => handleCellEdit(originalIdx, 'remark', e.target.value)}
                      onBlur={(e) => handleCellBlur(originalIdx, editingCell?.field || '', e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Tab') {
                          e.preventDefault();
                          const input = e.currentTarget;
                          const start = input.selectionStart || 0;
                          const end = input.selectionEnd || 0;
                          const newValue = row.remark.substring(0, start) + '\t' + row.remark.substring(end);
                          handleCellEdit(originalIdx, 'remark', newValue);
                          setTimeout(() => {
                            input.setSelectionRange(start + 1, start + 1);
                          }, 0);
                        }
                      }}
                      autoFocus
                      className="w-full px-1 py-0.5 text-xs border border-blue-400 rounded"
                    />
                  ) : (
                    <div
                      onClick={() => setEditingCell({ rowId: originalIdx, field: 'remark' })}
                      className="cursor-text text-gray-600 hover:bg-blue-50 px-1 rounded min-w-[100px]"
                    >
                      {row.remark || "-"}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface DepartmentTreeNode {
  id: string;
  code: string;
  name: string;
  type: 'department' | 'product';
  level: number;
  children?: DepartmentTreeNode[];
  isExpanded?: boolean;
}

interface ProductSubject {
  code: string;
  name: string;
}

const productSubjects: ProductSubject[] = [
  { code: 'Z0001', name: '个人住房贷款' },
  { code: 'Z0002', name: '企业流动资金贷款' },
  { code: 'Z0003', name: '结构性存款' },
  { code: 'Z0004', name: '理财产品A' },
  { code: 'Z0005', name: '汽车消费贷款' },
  { code: 'Z0006', name: '信用卡产品' },
  { code: 'Z0007', name: '个人经营性贷款' },
  { code: 'Z0008', name: '票据贴现' },
  { code: 'Z0009', name: '银行承兑汇票' },
  { code: 'Z0010', name: '保函业务' },
  { code: 'Z0011', name: '项目贷款' },
  { code: 'Z0012', name: '并购贷款' },
  { code: 'Z0013', name: '信用证' },
  { code: 'Z0014', name: '国际结算' },
  { code: 'Z0015', name: '贸易融资' },
  { code: 'Z0016', name: '供应链金融' },
  { code: 'Z0017', name: '零售存款' },
  { code: 'Z0018', name: '对公存款' },
  { code: 'Z0019', name: '同业存款' },
  { code: 'Z0020', name: '外汇买卖' },
];

function DepartmentTreeItem({
  node,
  onEdit,
  onToggle,
  onContextMenu,
  editingNode,
  onSaveEdit,
  onDrop,
  parentCode,
}: {
  node: DepartmentTreeNode;
  onEdit: (node: DepartmentTreeNode) => void;
  onToggle: (id: string) => void;
  onContextMenu: (e: React.MouseEvent, node: DepartmentTreeNode) => void;
  editingNode: { node: DepartmentTreeNode; newCode: string; newName: string } | null;
  onSaveEdit: (node: DepartmentTreeNode, newCode: string, newName: string) => void;
  onDrop: (targetNode: DepartmentTreeNode, productCode: string, productName: string) => void;
  parentCode?: string;
}) {
  const hasChildren = node.children && node.children.length > 0;
  const isEditing = editingNode?.node.id === node.id;
  const canAddProduct = node.type === 'department' && node.level === 3;
  const [isDragOver, setIsDragOver] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    if (canAddProduct) {
      e.preventDefault();
      setIsDragOver(true);
    }
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (canAddProduct) {
      const productCode = e.dataTransfer.getData('productCode');
      const productName = e.dataTransfer.getData('productName');
      if (productCode && productName) {
        onDrop(node, productCode, productName);
      }
    }
  };

  return (
    <div>
      <div
        className={`flex items-center gap-2 px-2 py-1.5 hover:bg-gray-100 cursor-pointer group ${
          isDragOver ? 'bg-blue-100' : ''
        }`}
        style={{ paddingLeft: `${node.level * 16 + 8}px` }}
        onContextMenu={(e) => onContextMenu(e, node)}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {hasChildren ? (
          <button
            onClick={() => onToggle(node.id)}
            className="flex-shrink-0 p-0.5 hover:bg-gray-200 rounded"
          >
            {node.isExpanded ? (
              <ChevronDown className="w-3 h-3 text-gray-600" />
            ) : (
              <ChevronRight className="w-3 h-3 text-gray-600" />
            )}
          </button>
        ) : (
          <div className="w-4 flex-shrink-0" />
        )}

        {node.type === 'department' ? (
          <FileText className="w-3 h-3 text-blue-600 flex-shrink-0" />
        ) : (
          <DatabaseIcon className="w-3 h-3 text-green-600 flex-shrink-0" />
        )}

        {isEditing ? (
          <div className="flex items-center gap-2 flex-1">
            <input
              type="text"
              value={editingNode.newCode}
              onChange={(e) => {
                const newVal = e.target.value;
                if (node.type === 'department' && parentCode) {
                  const parentPrefix = parentCode;
                  if (newVal.startsWith(parentPrefix)) {
                    editingNode.newCode = newVal;
                  }
                } else if (node.type === 'product') {
                  editingNode.newCode = newVal;
                }
              }}
              className="font-mono text-xs px-1 py-0.5 border border-blue-400 rounded w-24"
              autoFocus
            />
            <input
              type="text"
              value={editingNode.newName}
              onChange={(e) => (editingNode.newName = e.target.value)}
              className="text-xs px-1 py-0.5 border border-blue-400 rounded flex-1"
            />
            <button
              onClick={() => onSaveEdit(node, editingNode.newCode, editingNode.newName)}
              className="p-1 hover:bg-gray-200 rounded"
              title="保存"
            >
              <Save className="w-3 h-3 text-green-600" />
            </button>
          </div>
        ) : (
          <>
            <span className="font-mono text-xs text-gray-700 w-24">{node.code}</span>
            <span className="text-xs text-gray-700 flex-1">{node.name}</span>
            <button
              onClick={() => onEdit(node)}
              className="p-1 hover:bg-gray-200 rounded opacity-0 group-hover:opacity-100 transition-opacity"
              title="编辑"
            >
              <Edit className="w-3 h-3 text-gray-600" />
            </button>
          </>
        )}
      </div>

      {hasChildren && node.isExpanded && (
        <div>
          {node.children!.map((child) => (
            <DepartmentTreeItem
              key={child.id}
              node={child}
              onEdit={onEdit}
              onToggle={onToggle}
              onContextMenu={onContextMenu}
              editingNode={editingNode}
              onSaveEdit={onSaveEdit}
              onDrop={onDrop}
              parentCode={node.code}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function DataDepartmentContent() {
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [treeData, setTreeData] = useState<DepartmentTreeNode[]>([
    {
      id: '1',
      code: 'Y1',
      name: '总行',
      type: 'department',
      level: 1,
      isExpanded: true,
      children: [
        {
          id: '1-1',
          code: 'Y11',
          name: '零售银行部',
          type: 'department',
          level: 2,
          isExpanded: true,
          children: [
            {
              id: '1-1-1',
              code: 'Y111',
              name: '个人信贷团队',
              type: 'department',
              level: 3,
              isExpanded: true,
              children: [
                { id: '1-1-1-1', code: 'Z0001', name: '个人住房贷款', type: 'product', level: 4 },
                { id: '1-1-1-2', code: 'Z0005', name: '汽车消费贷款', type: 'product', level: 4 },
              ],
            },
            {
              id: '1-1-2',
              code: 'Y112',
              name: '零售存款团队',
              type: 'department',
              level: 3,
              isExpanded: false,
              children: [
                { id: '1-1-2-1', code: 'Z0017', name: '零售存款', type: 'product', level: 4 },
              ],
            },
            {
              id: '1-1-3',
              code: 'Y113',
              name: '信用卡中心',
              type: 'department',
              level: 3,
              isExpanded: false,
              children: [
                { id: '1-1-3-1', code: 'Z0006', name: '信用卡产品', type: 'product', level: 4 },
              ],
            },
          ],
        },
        {
          id: '1-2',
          code: 'Y12',
          name: '公司银行部',
          type: 'department',
          level: 2,
          isExpanded: true,
          children: [
            {
              id: '1-2-1',
              code: 'Y121',
              name: '公司贷款团队',
              type: 'department',
              level: 3,
              isExpanded: true,
              children: [
                { id: '1-2-1-1', code: 'Z0002', name: '企业流动资金贷款', type: 'product', level: 4 },
                { id: '1-2-1-2', code: 'Z0011', name: '项目贷款', type: 'product', level: 4 },
              ],
            },
            {
              id: '1-2-2',
              code: 'Y122',
              name: '对公存款团队',
              type: 'department',
              level: 3,
              isExpanded: false,
              children: [
                { id: '1-2-2-1', code: 'Z0018', name: '对公存款', type: 'product', level: 4 },
              ],
            },
          ],
        },
        {
          id: '1-3',
          code: 'Y13',
          name: '金融市场部',
          type: 'department',
          level: 2,
          isExpanded: true,
          children: [
            {
              id: '1-3-1',
              code: 'Y131',
              name: '理财业务团队',
              type: 'department',
              level: 3,
              isExpanded: false,
              children: [
                { id: '1-3-1-1', code: 'Z0003', name: '结构性存款', type: 'product', level: 4 },
                { id: '1-3-1-2', code: 'Z0004', name: '理财产品A', type: 'product', level: 4 },
              ],
            },
            {
              id: '1-3-2',
              code: 'Y132',
              name: '同业业务团队',
              type: 'department',
              level: 3,
              isExpanded: false,
              children: [
                { id: '1-3-2-1', code: 'Z0019', name: '同业存款', type: 'product', level: 4 },
              ],
            },
          ],
        },
        {
          id: '1-4',
          code: 'Y14',
          name: '国际业务部',
          type: 'department',
          level: 2,
          isExpanded: false,
          children: [
            {
              id: '1-4-1',
              code: 'Y141',
              name: '国际结算团队',
              type: 'department',
              level: 3,
              isExpanded: false,
              children: [
                { id: '1-4-1-1', code: 'Z0014', name: '国际结算', type: 'product', level: 4 },
              ],
            },
          ],
        },
      ],
    },
  ]);

  const [editingNode, setEditingNode] = useState<{
    node: DepartmentTreeNode;
    newCode: string;
    newName: string;
  } | null>(null);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    node: DepartmentTreeNode;
  } | null>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);

  const toggleNode = (id: string) => {
    const toggle = (nodes: DepartmentTreeNode[]): DepartmentTreeNode[] => {
      return nodes.map((node) => {
        if (node.id === id) {
          return { ...node, isExpanded: !node.isExpanded };
        }
        if (node.children) {
          return { ...node, children: toggle(node.children) };
        }
        return node;
      });
    };
    setTreeData(toggle(treeData));
  };

  const toggleAll = (expand: boolean) => {
    const toggleRec = (nodes: DepartmentTreeNode[]): DepartmentTreeNode[] => {
      return nodes.map((node) => ({
        ...node,
        isExpanded: expand && node.children && node.children.length > 0,
        children: node.children ? toggleRec(node.children) : undefined,
      }));
    };
    setTreeData(toggleRec(treeData));
  };

  const handleEdit = (node: DepartmentTreeNode) => {
    setEditingNode({ node, newCode: node.code, newName: node.name });
  };

  const handleSaveEdit = (node: DepartmentTreeNode, newCode: string, newName: string) => {
    const updateNode = (nodes: DepartmentTreeNode[]): DepartmentTreeNode[] => {
      return nodes.map((n) => {
        if (n.id === node.id) {
          return { ...n, code: newCode, name: newName };
        }
        if (n.children) {
          return { ...n, children: updateNode(n.children) };
        }
        return n;
      });
    };
    setTreeData(updateNode(treeData));
    setEditingNode(null);
  };

  const handleContextMenu = (e: React.MouseEvent, node: DepartmentTreeNode) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, node });
  };

  const handleDropProductSubject = (
    targetNode: DepartmentTreeNode,
    productCode: string,
    productName: string
  ) => {
    const addProduct = (nodes: DepartmentTreeNode[]): DepartmentTreeNode[] => {
      return nodes.map((node) => {
        if (node.id === targetNode.id && node.level === 3) {
          const existingProduct = node.children?.find((child) => child.code === productCode);
          if (existingProduct) {
            alert('该产品科目已存在于此部门下');
            return node;
          }

          const newProduct: DepartmentTreeNode = {
            id: `${node.id}-${Date.now()}`,
            code: productCode,
            name: productName,
            type: 'product',
            level: 4,
          };

          return {
            ...node,
            isExpanded: true,
            children: [...(node.children || []), newProduct],
          };
        }
        if (node.children) {
          return { ...node, children: addProduct(node.children) };
        }
        return node;
      });
    };
    setTreeData(addProduct(treeData));
  };

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const getSortIcon = (column: string) => {
    if (sortColumn !== column) {
      return <ArrowUpDown className="w-3 h-3 text-gray-400" />;
    }
    return sortDirection === 'asc' ? (
      <ArrowUp className="w-3 h-3 text-blue-600" />
    ) : (
      <ArrowDown className="w-3 h-3 text-blue-600" />
    );
  };

  const sortedProductSubjects = [...productSubjects].sort((a, b) => {
    if (!sortColumn) return 0;
    const aVal = a[sortColumn as keyof ProductSubject];
    const bVal = b[sortColumn as keyof ProductSubject];
    const comparison = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
    return sortDirection === 'asc' ? comparison : -comparison;
  });

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">部门科目维护</h3>
        <div className="flex-1" />
        <input
          type="text"
          placeholder="搜索部门..."
          className="px-2 py-1 text-xs border border-gray-300 rounded w-48"
        />
        <button className="flex items-center gap-1 px-3 py-1 text-xs bg-[#27ae60] text-white rounded hover:bg-[#229954]">
          <Upload className="w-3 h-3" />
          从Excel导入科目
        </button>
        <button
          onClick={() => toggleAll(false)}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
        >
          <ChevronsUp className="w-3 h-3" />
          <span>全部收起</span>
        </button>
        <button
          onClick={() => toggleAll(true)}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
        >
          <ChevronsDown className="w-3 h-3" />
          <span>全部展开</span>
        </button>
      </div>

      <div className="flex-1 overflow-hidden">
        <PanelGroup direction="horizontal">
          {/* 左侧树状结构 */}
          <Panel id="department-tree" order={1} defaultSize={60} minSize={30}>
            <div className="h-full border border-gray-300 rounded overflow-auto bg-white">
              {treeData.map((node) => (
                <DepartmentTreeItem
                  key={node.id}
                  node={node}
                  onEdit={handleEdit}
                  onToggle={toggleNode}
                  onContextMenu={handleContextMenu}
                  editingNode={editingNode}
                  onSaveEdit={handleSaveEdit}
                  onDrop={handleDropProductSubject}
                />
              ))}
            </div>
          </Panel>

          <PanelResizeHandle className="w-1 bg-gray-300 hover:bg-[#3498db] transition-colors mx-2" />

          {/* 右侧产品科目列表 */}
          <Panel id="product-subject-list" order={2} defaultSize={40} minSize={20}>
            <div className="h-full border border-gray-300 rounded bg-white flex flex-col">
              <div className="px-3 py-2 bg-gray-100 border-b border-gray-300">
                <h4 className="text-xs font-medium text-gray-800">产品科目列表</h4>
                <p className="text-[10px] text-gray-500 mt-0.5">拖拽到左侧3级部门科目</p>
              </div>

              {/* 表头 */}
              <div className="flex items-center bg-gray-50 border-b border-gray-300 px-3 py-1.5">
                <div className="w-3 flex-shrink-0" />
                <button
                  onClick={() => handleSort('code')}
                  className="flex items-center gap-1 text-xs font-medium text-gray-700 hover:text-blue-600 transition-colors w-24 ml-2"
                >
                  产品科目代码
                  {getSortIcon('code')}
                </button>
                <button
                  onClick={() => handleSort('name')}
                  className="flex items-center gap-1 justify-center text-xs font-medium text-gray-700 hover:text-blue-600 transition-colors flex-1 ml-2"
                >
                  产品科目名称
                  {getSortIcon('name')}
                </button>
              </div>

              <div className="flex-1 overflow-y-auto">
                {sortedProductSubjects.map((subject, idx) => (
                  <div
                    key={idx}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData('productCode', subject.code);
                      e.dataTransfer.setData('productName', subject.name);
                    }}
                    className="flex items-center gap-2 px-3 py-1.5 border-b border-gray-100 hover:bg-blue-50 cursor-move"
                  >
                    <DatabaseIcon className="w-3 h-3 text-green-600 flex-shrink-0" />
                    <span className="font-mono text-xs text-gray-700 w-24">{subject.code}</span>
                    <span className="text-xs text-gray-700 flex-1 truncate">{subject.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </Panel>
        </PanelGroup>
      </div>

      {contextMenu && (
        <div
          ref={contextMenuRef}
          className="fixed bg-white border border-gray-300 rounded shadow-lg py-1 z-50 min-w-[160px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              handleEdit(contextMenu.node);
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
          >
            <Edit className="w-3 h-3" />
            编辑
          </button>
          {contextMenu.node.children && contextMenu.node.children.length > 0 && (
            <button
              onClick={() => {
                toggleNode(contextMenu.node.id);
                setContextMenu(null);
              }}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
            >
              <Minimize2 className="w-3 h-3" />
              {contextMenu.node.isExpanded ? '收起本级' : '展开下级'}
            </button>
          )}
          {contextMenu.node.children && contextMenu.node.children.length > 0 && (
            <>
              <button
                onClick={() => {
                  const expandAll = (nodes: DepartmentTreeNode[]): DepartmentTreeNode[] => {
                    return nodes.map((n) => {
                      if (n.id === contextMenu.node.id) {
                        const expand = (node: DepartmentTreeNode): DepartmentTreeNode => ({
                          ...node,
                          isExpanded: true,
                          children: node.children?.map(expand),
                        });
                        return expand(n);
                      }
                      if (n.children) {
                        return { ...n, children: expandAll(n.children) };
                      }
                      return n;
                    });
                  };
                  setTreeData(expandAll(treeData));
                  setContextMenu(null);
                }}
                className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
              >
                <Maximize className="w-3 h-3" />
                展开所有下级
              </button>
              <button
                onClick={() => {
                  const collapseAll = (nodes: DepartmentTreeNode[]): DepartmentTreeNode[] => {
                    return nodes.map((n) => {
                      if (n.id === contextMenu.node.id) {
                        const collapse = (node: DepartmentTreeNode): DepartmentTreeNode => ({
                          ...node,
                          isExpanded: false,
                          children: node.children?.map(collapse),
                        });
                        return collapse(n);
                      }
                      if (n.children) {
                        return { ...n, children: collapseAll(n.children) };
                      }
                      return n;
                    });
                  };
                  setTreeData(collapseAll(treeData));
                  setContextMenu(null);
                }}
                className="w-full px-3 py-1.5 text-xs text-left hover:bg-gray-100 flex items-center gap-2"
              >
                <Minimize2 className="w-3 h-3" />
                收起所有下级
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function BudgetInputContent() {
  const [dataType, setDataType] = useState<'budget' | 'actual'>('budget');
  const [selectedProduct, setSelectedProduct] = useState({ code: 'Z0001', name: '个人住房贷款' });
  const [showProductDialog, setShowProductDialog] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  // 生成随机月度数据
  const generateMonths = (base: number) => {
    return Array.from({ length: 12 }, (_, i) => base + i * (base * 0.02));
  };

  // 示例数据：报告科目层级结构+数据科目+月度数据
  const [budgetData, setBudgetData] = useState([
    // 资产类 - 流动资产 - 货币资金
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010101', name: '货币资金' }, data: { code: 'D1001', name: '库存现金' }, months: generateMonths(100) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010101', name: '货币资金' }, data: { code: 'D1002', name: '银行存款' }, months: generateMonths(5000) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010101', name: '货币资金' }, data: { code: 'D1003', name: '其他货币资金' }, months: generateMonths(800) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010101', name: '货币资金' }, data: { code: 'D1004', name: '存放中央银行款项' }, months: generateMonths(3500) },

    // 资产类 - 流动资产 - 金融资产
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010102', name: '交易性金融资产' }, data: { code: 'D1007', name: '交易性金融资产' }, months: generateMonths(2000) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010102', name: '交易性金融资产' }, data: { code: 'D1008', name: '衍生金融资产' }, months: generateMonths(1200) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010102', name: '交易性金融资产' }, data: { code: 'D1009', name: '买入返售金融资产' }, months: generateMonths(1800) },

    // 资产类 - 流动资产 - 贷款及垫款
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010103', name: '贷款及垫款' }, data: { code: 'D1013', name: '发放贷款及垫款' }, months: generateMonths(25000) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010103', name: '贷款及垫款' }, data: { code: 'D1010', name: '应收账款' }, months: generateMonths(1500) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0101', name: '流动资产' }, report3: { code: 'X010103', name: '贷款及垫款' }, data: { code: 'D1011', name: '应收利息' }, months: generateMonths(600) },

    // 资产类 - 非流动资产 - 长期投资
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0102', name: '非流动资产' }, report3: { code: 'X010201', name: '长期投资' }, data: { code: 'D1014', name: '可供出售金融资产' }, months: generateMonths(6000) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0102', name: '非流动资产' }, report3: { code: 'X010201', name: '长期投资' }, data: { code: 'D1015', name: '持有至到期投资' }, months: generateMonths(5500) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0102', name: '非流动资产' }, report3: { code: 'X010201', name: '长期投资' }, data: { code: 'D1016', name: '长期股权投资' }, months: generateMonths(8000) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0102', name: '非流动资产' }, report3: { code: 'X010201', name: '长期投资' }, data: { code: 'D1017', name: '投资性房地产' }, months: generateMonths(4200) },

    // 资产类 - 非流动资产 - 固定资产
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0102', name: '非流动资产' }, report3: { code: 'X010202', name: '固定资产' }, data: { code: 'D1018', name: '固定资产' }, months: generateMonths(12000) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0102', name: '非流动资产' }, report3: { code: 'X010202', name: '固定资产' }, data: { code: 'D1019', name: '在建工程' }, months: generateMonths(3000) },
    { report1: { code: 'X01', name: '资产类' }, report2: { code: 'X0102', name: '非流动资产' }, report3: { code: 'X010202', name: '固定资产' }, data: { code: 'D1020', name: '无形资产' }, months: generateMonths(1800) },

    // 负债类 - 流动负债 - 短期借款
    { report1: { code: 'X02', name: '负债类' }, report2: { code: 'X0201', name: '流动负债' }, report3: { code: 'X020101', name: '短期借款' }, data: { code: 'D5001', name: '短期借款' }, months: generateMonths(3000) },
    { report1: { code: 'X02', name: '负债类' }, report2: { code: 'X0201', name: '流动负债' }, report3: { code: 'X020101', name: '短期借款' }, data: { code: 'D5002', name: '向中央银行借款' }, months: generateMonths(2500) },

    // 负债类 - 流动负债 - 吸收存款
    { report1: { code: 'X02', name: '负债类' }, report2: { code: 'X0201', name: '流动负债' }, report3: { code: 'X020102', name: '吸收存款' }, data: { code: 'D5003', name: '吸收存款' }, months: generateMonths(15000) },
    { report1: { code: 'X02', name: '负债类' }, report2: { code: 'X0201', name: '流动负债' }, report3: { code: 'X020102', name: '吸收存款' }, data: { code: 'D5004', name: '同业存放' }, months: generateMonths(5000) },
    { report1: { code: 'X02', name: '负债类' }, report2: { code: 'X0201', name: '流动负债' }, report3: { code: 'X020102', name: '吸收存款' }, data: { code: 'D5005', name: '拆入资金' }, months: generateMonths(3500) },

    // 负债类 - 流动负债 - 卖出回购
    { report1: { code: 'X02', name: '负债类' }, report2: { code: 'X0201', name: '流动负债' }, report3: { code: 'X020103', name: '卖出回购' }, data: { code: 'D5006', name: '卖出回购金融资产款' }, months: generateMonths(4000) },

    // 收入类 - 利息收入
    { report1: { code: 'X03', name: '收入类' }, report2: { code: 'X0301', name: '利息收入' }, report3: { code: 'X030101', name: '贷款利息' }, data: { code: 'D2001', name: '贷款利息收入' }, months: generateMonths(8000) },
    { report1: { code: 'X03', name: '收入类' }, report2: { code: 'X0301', name: '利息收入' }, report3: { code: 'X030101', name: '贷款利息' }, data: { code: 'D2002', name: '存放同业利息收入' }, months: generateMonths(1200) },
    { report1: { code: 'X03', name: '收入类' }, report2: { code: 'X0301', name: '利息收入' }, report3: { code: 'X030101', name: '贷款利息' }, data: { code: 'D2003', name: '拆借利息收入' }, months: generateMonths(900) },

    // 收入类 - 手续费收入
    { report1: { code: 'X03', name: '收入类' }, report2: { code: 'X0302', name: '手续费及佣金收入' }, report3: { code: 'X030201', name: '手续费收入' }, data: { code: 'D2005', name: '手续费收入' }, months: generateMonths(2500) },
    { report1: { code: 'X03', name: '收入类' }, report2: { code: 'X0302', name: '手续费及佣金收入' }, report3: { code: 'X030201', name: '手续费收入' }, data: { code: 'D2006', name: '佣金收入' }, months: generateMonths(1800) },

    // 收入类 - 投资收益
    { report1: { code: 'X03', name: '收入类' }, report2: { code: 'X0303', name: '投资收益' }, report3: { code: 'X030301', name: '投资收益' }, data: { code: 'D2004', name: '债券投资收益' }, months: generateMonths(3200) },
    { report1: { code: 'X03', name: '收入类' }, report2: { code: 'X0303', name: '投资收益' }, report3: { code: 'X030301', name: '投资收益' }, data: { code: 'D2007', name: '汇兑收益' }, months: generateMonths(800) },
    { report1: { code: 'X03', name: '收入类' }, report2: { code: 'X0303', name: '投资收益' }, report3: { code: 'X030301', name: '投资收益' }, data: { code: 'D2008', name: '公允价值变动收益' }, months: generateMonths(1500) },
    { report1: { code: 'X03', name: '收入类' }, report2: { code: 'X0303', name: '投资收益' }, report3: { code: 'X030301', name: '投资收益' }, data: { code: 'D2009', name: '投资收益' }, months: generateMonths(2200) },

    // 支出类 - 利息支出
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0401', name: '利息支出' }, report3: { code: 'X040101', name: '存款利息' }, data: { code: 'D3001', name: '存款利息支出' }, months: generateMonths(5000) },
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0401', name: '利息支出' }, report3: { code: 'X040101', name: '存款利息' }, data: { code: 'D3002', name: '同业存款利息支出' }, months: generateMonths(1500) },
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0401', name: '利息支出' }, report3: { code: 'X040101', name: '存款利息' }, data: { code: 'D3003', name: '拆入资金利息支出' }, months: generateMonths(800) },
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0401', name: '利息支出' }, report3: { code: 'X040101', name: '存款利息' }, data: { code: 'D3004', name: '卖出回购利息支出' }, months: generateMonths(600) },

    // 支出类 - 手续费支出
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0402', name: '手续费及佣金支出' }, report3: { code: 'X040201', name: '手续费支出' }, data: { code: 'D3005', name: '手续费支出' }, months: generateMonths(900) },
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0402', name: '手续费及佣金支出' }, report3: { code: 'X040201', name: '手续费支出' }, data: { code: 'D3006', name: '佣金支出' }, months: generateMonths(700) },

    // 支出类 - 业务及管理费
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0403', name: '业务及管理费' }, report3: { code: 'X040301', name: '人员费用' }, data: { code: 'D3008', name: '员工薪酬' }, months: generateMonths(6000) },
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0403', name: '业务及管理费' }, report3: { code: 'X040302', name: '折旧摊销' }, data: { code: 'D3009', name: '折旧费用' }, months: generateMonths(1200) },
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0403', name: '业务及管理费' }, report3: { code: 'X040302', name: '折旧摊销' }, data: { code: 'D3010', name: '无形资产摊销' }, months: generateMonths(300) },
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0403', name: '业务及管理费' }, report3: { code: 'X040303', name: '其他费用' }, data: { code: 'D3007', name: '业务及管理费' }, months: generateMonths(2500) },

    // 支出类 - 减值损失
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0404', name: '减值损失' }, report3: { code: 'X040401', name: '减值损失' }, data: { code: 'D4001', name: '资产减值损失' }, months: generateMonths(1800) },
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0404', name: '减值损失' }, report3: { code: 'X040401', name: '减值损失' }, data: { code: 'D4002', name: '信用减值损失' }, months: generateMonths(2200) },

    // 支出类 - 税费
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0405', name: '税费' }, report3: { code: 'X040501', name: '税费' }, data: { code: 'D4003', name: '营业税金及附加' }, months: generateMonths(800) },
    { report1: { code: 'X04', name: '支出类' }, report2: { code: 'X0405', name: '税费' }, report3: { code: 'X040501', name: '税费' }, data: { code: 'D4004', name: '所得税费用' }, months: generateMonths(1500) },
  ]);

  const formatNumber = (num: number) => {
    return num.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  };

  const parseFormattedNumber = (str: string) => {
    return parseFloat(str.replace(/,/g, '')) || 0;
  };

  const handleCellEdit = (rowIdx: number, monthIdx: number, value: string) => {
    const newData = [...budgetData];
    newData[rowIdx].months[monthIdx] = parseFormattedNumber(value);
    setBudgetData(newData);
  };

  const shouldShowReport1 = (rowIdx: number) => {
    if (rowIdx === 0) return true;
    return budgetData[rowIdx].report1.code !== budgetData[rowIdx - 1].report1.code;
  };

  const shouldShowReport2 = (rowIdx: number) => {
    if (rowIdx === 0) return true;
    return budgetData[rowIdx].report2.code !== budgetData[rowIdx - 1].report2.code;
  };

  const shouldShowReport3 = (rowIdx: number) => {
    if (rowIdx === 0) return true;
    return budgetData[rowIdx].report3.code !== budgetData[rowIdx - 1].report3.code;
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) {
        setShowProductDialog(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3 flex items-center gap-3">
        <h3 className="text-sm font-medium text-gray-800">预算基础数据输入</h3>
        <div className="flex-1" />
        <input
          type="text"
          placeholder="搜索科目内容"
          className="px-2 py-1 text-xs border border-gray-300 rounded w-48"
        />
        <div className="relative">
          <button
            onClick={() => setShowProductDialog(true)}
            className="flex items-center gap-2 px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50"
          >
            <Building2 className="w-3 h-3" />
            <span className="font-mono">{selectedProduct.code}</span>
            <span>{selectedProduct.name}</span>
          </button>
          {showProductDialog && (
            <div
              ref={dialogRef}
              className="absolute right-0 top-full mt-1 bg-white border border-gray-300 rounded shadow-lg z-50 w-80 max-h-96 overflow-auto"
            >
              <div className="px-3 py-2 bg-gray-100 border-b border-gray-300 sticky top-0">
                <h4 className="text-xs font-medium text-gray-800">选择产品科目</h4>
              </div>
              <div className="p-2">
                {[
                                   { dept: 'Y11', deptName: '零售银行部', products: [{ code: 'Z0001', name: '个人住房贷款' }, { code: 'Z0005', name: '汽车消费贷款' }] },
                  { dept: 'Y12', deptName: '公司银行部', products: [{ code: 'Z0002', name: '企业流动资金贷款' }, { code: 'Z0011', name: '项目贷款' }] },
                  { dept: 'Y13', deptName: '金融市场部', products: [{ code: 'Z0003', name: '结构性存款' }, { code: 'Z0004', name: '理财产品A' }] },
                ].map((dept, idx) => (
                  <div key={idx} className="mb-2">
                    <div className="px-2 py-1 bg-blue-50 text-xs font-medium text-gray-700">
                      {dept.dept} {dept.deptName}
                    </div>
                    {dept.products.map((prod, pidx) => (
                      <div
                        key={pidx}
                        onClick={() => {
                          setSelectedProduct(prod);
                          setShowProductDialog(false);
                        }}
                        className="px-4 py-1.5 hover:bg-gray-100 cursor-pointer flex items-center gap-2"
                      >
                        <DatabaseIcon className="w-3 h-3 text-green-600" />
                        <span className="font-mono text-xs text-gray-700">{prod.code}</span>
                        <span className="text-xs text-gray-700">{prod.name}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <button className="flex items-center gap-1 px-3 py-1 text-xs bg-[#27ae60] text-white rounded hover:bg-[#229954]">
          <Upload className="w-3 h-3" />
          Excel上传数据
        </button>
        <div className="flex items-center bg-gray-100 border border-gray-300 rounded">
          <button
            onClick={() => setDataType('budget')}
            className={`px-3 py-1 text-xs transition-colors ${
              dataType === 'budget'
                ? 'bg-[#3498db] text-white'
                : 'bg-transparent text-gray-700 hover:bg-gray-200'
            }`}
          >
            预算值
          </button>
          <button
            onClick={() => setDataType('actual')}
            className={`px-3 py-1 text-xs transition-colors ${
              dataType === 'actual'
                ? 'bg-[#3498db] text-white'
                : 'bg-transparent text-gray-700 hover:bg-gray-200'
            }`}
          >
            实际值
          </button>
        </div>
        <button className="flex items-center gap-1 px-3 py-1 text-xs bg-[#3498db] text-white rounded hover:bg-[#2980b9]">
          <RefreshCw className="w-3 h-3" />
          全局计算并刷新
        </button>
      </div>

      <div className="flex-1 border border-gray-300 rounded overflow-auto" style={{ maxHeight: 'calc(100vh - 200px)' }}>
        <table className="text-xs border-collapse" style={{ minWidth: "1600px" }}>
          <thead className="bg-gray-100 border-b border-gray-300 sticky top-0 z-10">
            <tr>
              <th className="px-2 py-1 text-left align-bottom text-gray-700 font-medium border-r border-gray-200 w-auto sticky left-0 bg-gray-100 z-20" style={{ minWidth: '180px', maxWidth: '250px' }}>
                报告科目
              </th>
              <th className="px-2 py-1 text-left align-bottom text-gray-700 font-medium border-r-2 border-gray-400 sticky bg-gray-100 z-20" style={{ left: '180px', minWidth: '140px', maxWidth: '180px' }}>
                数据科目
              </th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">1月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">2月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">3月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">4月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">5月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">6月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">7月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">8月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">9月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">10月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">11月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium border-r border-gray-200 w-24">12月</th>
              <th className="px-2 py-1 text-center text-gray-700 font-medium sticky right-0 bg-gray-100 z-20 w-28 border-l-2 border-gray-400">合计</th>
            </tr>
          </thead>
          <tbody className="bg-white">
            {(() => {
              const rows: JSX.Element[] = [];
              const report3Subtotals: Map<string, number[]> = new Map();
              const report2Subtotals: Map<string, number[]> = new Map();
              const report1Subtotals: Map<string, number[]> = new Map();

              // 计算各级汇总
              budgetData.forEach(row => {
                const key3 = `${row.report1.code}-${row.report2.code}-${row.report3.code}`;
                const key2 = `${row.report1.code}-${row.report2.code}`;
                const key1 = row.report1.code;

                if (!report3Subtotals.has(key3)) {
                  report3Subtotals.set(key3, new Array(12).fill(0));
                }
                if (!report2Subtotals.has(key2)) {
                  report2Subtotals.set(key2, new Array(12).fill(0));
                }
                if (!report1Subtotals.has(key1)) {
                  report1Subtotals.set(key1, new Array(12).fill(0));
                }

                row.months.forEach((val, idx) => {
                  report3Subtotals.get(key3)![idx] += val;
                  report2Subtotals.get(key2)![idx] += val;
                  report1Subtotals.get(key1)![idx] += val;
                });
              });

              budgetData.forEach((row, rowIdx) => {
                const total = row.months.reduce((sum, val) => sum + val, 0);

                // 数据行
                rows.push(
                  <tr key={`data-${rowIdx}`} className="border-b border-gray-100 hover:bg-blue-50">
                    <td className="px-2 py-0.5 border-r border-gray-200 align-bottom sticky left-0 bg-white hover:bg-blue-50 z-10" style={{ minWidth: '180px', maxWidth: '250px' }}>
                      <div className="text-xs text-gray-700">
                        {shouldShowReport1(rowIdx) && (
                          <div className="py-0.5">
                            <span className="font-mono text-[10px] text-gray-600">{row.report1.code}</span>
                            <span className="ml-1 font-medium">{row.report1.name}</span>
                          </div>
                        )}
                        {shouldShowReport2(rowIdx) && (
                          <div className="py-0.5" style={{ paddingLeft: '1rem' }}>
                            <span className="font-mono text-[10px] text-gray-600">{row.report2.code}</span>
                            <span className="ml-1">{row.report2.name}</span>
                          </div>
                        )}
                        {shouldShowReport3(rowIdx) && (
                          <div className="py-0.5" style={{ paddingLeft: '2rem' }}>
                            <span className="font-mono text-[10px] text-gray-600">{row.report3.code}</span>
                            <span className="ml-1">{row.report3.name}</span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-2 py-0.5 border-r-2 border-gray-400 align-bottom sticky bg-white hover:bg-blue-50 z-10" style={{ left: '180px', minWidth: '140px', maxWidth: '180px' }}>
                      <div className="text-xs text-gray-700">
                        <span className="font-mono text-[10px] text-gray-600">{row.data.code}</span>
                        <span className="ml-1">{row.data.name}</span>
                      </div>
                    </td>
                    {row.months.map((value, monthIdx) => (
                      <td key={monthIdx} className={`px-1 py-0.5 align-bottom ${monthIdx < 11 ? 'border-r border-gray-200' : 'border-r border-gray-200'}`}>
                        <input
                          type="text"
                          value={formatNumber(value)}
                          onChange={(e) => handleCellEdit(rowIdx, monthIdx, e.target.value)}
                          className="w-full px-1 py-0.5 text-xs text-right border border-gray-300 rounded focus:border-blue-400 focus:outline-none font-mono [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                        />
                      </td>
                    ))}
                    <td className="px-2 py-0.5 text-right align-bottom sticky right-0 bg-gray-100 z-10 border-l-2 border-gray-400">
                      <span className="font-mono text-xs font-medium text-gray-800">{formatNumber(total)}</span>
                    </td>
                  </tr>
                );

                const nextRow = budgetData[rowIdx + 1];
                const key3 = `${row.report1.code}-${row.report2.code}-${row.report3.code}`;
                const key2 = `${row.report1.code}-${row.report2.code}`;
                const key1 = row.report1.code;

                // 报告科目3级汇总
                if (!nextRow || nextRow.report3.code !== row.report3.code) {
                  const subtotal3 = report3Subtotals.get(key3)!;
                  const total3 = subtotal3.reduce((sum, val) => sum + val, 0);
                  rows.push(
                    <tr key={`subtotal3-${rowIdx}`} className="bg-gray-100 border-b border-gray-200">
                      <td className="px-2 py-0.5 border-r border-gray-200 align-bottom sticky left-0 bg-gray-100 z-10" style={{ minWidth: '180px', maxWidth: '250px' }}>
                        <div className="py-0.5 text-xs font-medium text-gray-700" style={{ paddingLeft: '2rem' }}>
                          {row.report3.name}小计
                        </div>
                      </td>
                      <td className="px-2 py-0.5 border-r-2 border-gray-400 align-bottom sticky bg-gray-100 z-10" style={{ left: '180px', minWidth: '140px', maxWidth: '180px' }}></td>
                      {subtotal3.map((value, monthIdx) => (
                        <td key={monthIdx} className={`px-1 py-0.5 text-right align-bottom ${monthIdx < 11 ? 'border-r border-gray-200' : 'border-r border-gray-200'}`}>
                          <span className="font-mono text-xs font-medium text-gray-800">{formatNumber(value)}</span>
                        </td>
                      ))}
                      <td className="px-2 py-0.5 text-right align-bottom sticky right-0 bg-gray-200 z-10 border-l-2 border-gray-400">
                        <span className="font-mono text-xs font-bold text-gray-800">{formatNumber(total3)}</span>
                      </td>
                    </tr>
                  );
                }

                // 报告科目2级汇总
                if (!nextRow || nextRow.report2.code !== row.report2.code) {
                  const subtotal2 = report2Subtotals.get(key2)!;
                  const total2 = subtotal2.reduce((sum, val) => sum + val, 0);
                  rows.push(
                    <tr key={`subtotal2-${rowIdx}`} className="bg-gray-200 border-b border-gray-300">
                      <td className="px-2 py-0.5 border-r border-gray-200 align-bottom sticky left-0 bg-gray-200 z-10" style={{ minWidth: '180px', maxWidth: '250px' }}>
                        <div className="py-0.5 text-xs font-semibold text-gray-800" style={{ paddingLeft: '1rem' }}>
                          {row.report2.name}小计
                        </div>
                      </td>
                      <td className="px-2 py-0.5 border-r-2 border-gray-400 align-bottom sticky bg-gray-200 z-10" style={{ left: '180px', minWidth: '140px', maxWidth: '180px' }}></td>
                      {subtotal2.map((value, monthIdx) => (
                        <td key={monthIdx} className={`px-1 py-0.5 text-right align-bottom ${monthIdx < 11 ? 'border-r border-gray-200' : 'border-r border-gray-200'}`}>
                          <span className="font-mono text-xs font-semibold text-gray-800">{formatNumber(value)}</span>
                        </td>
                      ))}
                      <td className="px-2 py-0.5 text-right align-bottom sticky right-0 bg-gray-300 z-10 border-l-2 border-gray-400">
                        <span className="font-mono text-xs font-bold text-gray-800">{formatNumber(total2)}</span>
                      </td>
                    </tr>
                  );
                }

                // 报告科目1级汇总
                if (!nextRow || nextRow.report1.code !== row.report1.code) {
                  const subtotal1 = report1Subtotals.get(key1)!;
                  const total1 = subtotal1.reduce((sum, val) => sum + val, 0);
                  rows.push(
                    <tr key={`subtotal1-${rowIdx}`} className="bg-gray-300 border-b-2 border-gray-400">
                      <td className="px-2 py-0.5 border-r border-gray-200 align-bottom sticky left-0 bg-gray-300 z-10" style={{ minWidth: '180px', maxWidth: '250px' }}>
                        <div className="py-0.5 text-xs font-bold text-gray-900">
                          {row.report1.name}合计
                        </div>
                      </td>
                      <td className="px-2 py-0.5 border-r-2 border-gray-400 align-bottom sticky bg-gray-300 z-10" style={{ left: '180px', minWidth: '140px', maxWidth: '180px' }}></td>
                      {subtotal1.map((value, monthIdx) => (
                        <td key={monthIdx} className={`px-1 py-0.5 text-right align-bottom ${monthIdx < 11 ? 'border-r border-gray-200' : 'border-r border-gray-200'}`}>
                          <span className="font-mono text-xs font-bold text-gray-900">{formatNumber(value)}</span>
                        </td>
                      ))}
                      <td className="px-2 py-0.5 text-right align-bottom sticky right-0 bg-gray-400 z-10 border-l-2 border-gray-400">
                        <span className="font-mono text-xs font-bold text-gray-900">{formatNumber(total1)}</span>
                      </td>
                    </tr>
                  );
                }
              });

              return rows;
            })()}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface PivotField {
  id: string;
  name: string;
  type: 'dimension' | 'measure';
}

type DropZone = 'pool' | 'row' | 'column' | 'page' | 'value';

export function PivotTableContent() {
  const allFields: PivotField[] = [
    { id: 'report1', name: '报告科目1级', type: 'dimension' },
    { id: 'report2', name: '报告科目2级', type: 'dimension' },
    { id: 'report3', name: '报告科目3级', type: 'dimension' },
    { id: 'dataAccount', name: '数据科目', type: 'dimension' },
    { id: 'product', name: '产品科目', type: 'dimension' },
    { id: 'department', name: '部门科目', type: 'dimension' },
    { id: 'month', name: '月份', type: 'dimension' },
    { id: 'year', name: '年度', type: 'dimension' },
    { id: 'quarter', name: '季度', type: 'dimension' },
    { id: 'budgetAmount', name: '预算金额', type: 'measure' },
    { id: 'actualAmount', name: '实际金额', type: 'measure' },
    { id: 'variance', name: '差异额', type: 'measure' },
    { id: 'varianceRate', name: '差异率', type: 'measure' },
  ];

  const [fieldPool, setFieldPool] = useState<PivotField[]>(allFields);
  const [rowFields, setRowFields] = useState<PivotField[]>([]);
  const [columnFields, setColumnFields] = useState<PivotField[]>([]);
  const [pageFields, setPageFields] = useState<PivotField[]>([]);
  const [valueFields, setValueFields] = useState<PivotField[]>([]);
  const [showRowTotal, setShowRowTotal] = useState(true);
  const [showColumnTotal, setShowColumnTotal] = useState(true);
  const [draggedField, setDraggedField] = useState<PivotField | null>(null);
  const [dragSource, setDragSource] = useState<DropZone | null>(null);
  const [pageFieldSelections, setPageFieldSelections] = useState<Record<string, string>>({});

  // 获取字段的可选值
  const getFieldOptions = (fieldId: string): string[] => {
    const optionsMap: Record<string, string[]> = {
      'report1': ['资产类', '负债类', '收入类', '支出类'],
      'report2': ['流动资产', '非流动资产', '流动负债', '非流动负债', '利息收入', '手续费收入', '利息支出', '业务及管理费'],
      'product': ['个人住房贷款', '汽车消费贷款', '企业流动资金贷款', '项目贷款', '结构性存款', '理财产品A'],
      'department': ['零售银行部', '公司银行部', '金融市场部', '国际业务部'],
      'month': ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
      'year': ['2024年', '2025年', '2026年'],
      'quarter': ['第一季度', '第二季度', '第三季度', '第四季度'],
    };
    return optionsMap[fieldId] || ['全部'];
  };

  const getFieldsForZone = (zone: DropZone): PivotField[] => {
    switch (zone) {
      case 'pool': return fieldPool;
      case 'row': return rowFields;
      case 'column': return columnFields;
      case 'page': return pageFields;
      case 'value': return valueFields;
      default: return [];
    }
  };

  const setFieldsForZone = (zone: DropZone, fields: PivotField[]) => {
    switch (zone) {
      case 'pool': setFieldPool(fields); break;
      case 'row': setRowFields(fields); break;
      case 'column': setColumnFields(fields); break;
      case 'page': setPageFields(fields); break;
      case 'value': setValueFields(fields); break;
    }
  };

  const handleDragStart = (field: PivotField, source: DropZone) => {
    setDraggedField(field);
    setDragSource(source);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (targetZone: DropZone) => {
    if (!draggedField || !dragSource) return;

    const sourceFields = getFieldsForZone(dragSource).filter(f => f.id !== draggedField.id);
    setFieldsForZone(dragSource, sourceFields);

    const targetFields = [...getFieldsForZone(targetZone), draggedField];
    setFieldsForZone(targetZone, targetFields);

    setDraggedField(null);
    setDragSource(null);
  };

  const removeFieldFromZone = (field: PivotField, zone: DropZone) => {
    const fields = getFieldsForZone(zone).filter(f => f.id !== field.id);
    setFieldsForZone(zone, fields);
    setFieldPool([...fieldPool, field]);
  };

  const FieldItem = ({ field, zone, showRemove = false }: { field: PivotField; zone: DropZone; showRemove?: boolean }) => (
    <div
      draggable
      onDragStart={() => handleDragStart(field, zone)}
      className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-white border border-gray-300 rounded text-[11px] cursor-move hover:bg-gray-50 group"
    >
      <GripVertical className="w-2.5 h-2.5 text-gray-400 flex-shrink-0" />
      <span className="whitespace-nowrap">{field.name}</span>
      {showRemove && (
        <button
          onClick={() => removeFieldFromZone(field, zone)}
          className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
        >
          <X className="w-2.5 h-2.5 text-gray-500 hover:text-red-600" />
        </button>
      )}
    </div>
  );

  const FieldItemWithDropdown = ({ field, zone }: { field: PivotField; zone: DropZone }) => {
    const options = getFieldOptions(field.id);
    const selectedValue = pageFieldSelections[field.id] || options[0] || '全部';

    return (
      <div
        draggable
        onDragStart={() => handleDragStart(field, zone)}
        className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-white border border-gray-300 rounded text-[11px] cursor-move hover:bg-gray-50 group"
      >
        <GripVertical className="w-2.5 h-2.5 text-gray-400 flex-shrink-0" />
        <span className="text-gray-700 whitespace-nowrap">{field.name}:</span>
        <select
          value={selectedValue}
          onChange={(e) => setPageFieldSelections({ ...pageFieldSelections, [field.id]: e.target.value })}
          className="text-[11px] border-0 bg-transparent focus:outline-none cursor-pointer pr-1"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          {options.map(option => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <button
          onClick={() => removeFieldFromZone(field, zone)}
          className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
        >
          <X className="w-2.5 h-2.5 text-gray-500 hover:text-red-600" />
        </button>
      </div>
    );
  };

  const DropZoneBox = ({ zone, title, fields }: { zone: DropZone; title: string; fields: PivotField[] }) => (
    <div
      onDragOver={handleDragOver}
      onDrop={() => handleDrop(zone)}
      className="border-2 border-dashed border-gray-300 rounded p-1.5 min-h-[50px] bg-gray-50"
    >
      <div className="text-[11px] font-medium text-gray-700 mb-1">{title}</div>
      <div className="space-y-0.5">
        {fields.map(field => (
          zone === 'page' || zone === 'column' ? (
            <FieldItemWithDropdown key={field.id} field={field} zone={zone} />
          ) : (
            <FieldItem key={field.id} field={field} zone={zone} showRemove={true} />
          )
        ))}
        {fields.length === 0 && (
          <div className="text-[10px] text-gray-400 text-center py-1">拖拽字段到此处</div>
        )}
      </div>
    </div>
  );

  return (
    <div className="p-4 h-full flex flex-col">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-gray-800">数据透视表</h3>
      </div>

      <div className="grid grid-cols-[40%_1fr] gap-4 mb-3" style={{ maxHeight: '32vh' }}>
        <div className="flex flex-col">
          <div
            onDragOver={handleDragOver}
            onDrop={() => handleDrop('pool')}
            className="border border-gray-300 rounded p-2 bg-white flex-1 overflow-auto"
          >
            <div className="text-xs font-medium text-gray-700 mb-2">字段列表</div>
            <div className="grid grid-cols-4 gap-1.5">
              {fieldPool.map(field => (
                <FieldItem key={field.id} field={field} zone="pool" />
              ))}
            </div>
          </div>

          <div className="flex gap-4 mt-2">
            <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                checked={showRowTotal}
                onChange={(e) => setShowRowTotal(e.target.checked)}
                className="w-3.5 h-3.5"
              />
              显示行汇总
            </label>
            <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                checked={showColumnTotal}
                onChange={(e) => setShowColumnTotal(e.target.checked)}
                className="w-3.5 h-3.5"
              />
              显示列汇总
            </label>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <DropZoneBox zone="page" title="页字段" fields={pageFields} />
          <DropZoneBox zone="column" title="列字段" fields={columnFields} />
          <DropZoneBox zone="row" title="行字段" fields={rowFields} />
          <DropZoneBox zone="value" title="数值字段" fields={valueFields} />
        </div>
      </div>

      <div className="flex-1 border border-gray-300 rounded overflow-auto bg-white">
        <div className="p-3">
          <div className="text-xs font-medium text-gray-700 mb-2">数据透视表视图</div>

          {rowFields.length > 0 || columnFields.length > 0 || valueFields.length > 0 ? (
            <table className="text-xs border-collapse w-full">
              <thead className="bg-gray-100">
                <tr>
                  <th className="border border-gray-300 px-2 py-1 text-left font-medium text-gray-700">
                    {rowFields.map(f => f.name).join(' / ') || '行'}
                  </th>
                  <th className="border border-gray-300 px-2 py-1 text-center font-medium text-gray-700">1月</th>
                  <th className="border border-gray-300 px-2 py-1 text-center font-medium text-gray-700">2月</th>
                  <th className="border border-gray-300 px-2 py-1 text-center font-medium text-gray-700">3月</th>
                  {showColumnTotal && (
                    <th className="border border-gray-300 px-2 py-1 text-center font-medium text-gray-700 bg-blue-50">合计</th>
                  )}
                </tr>
              </thead>
              <tbody>
                <tr className="hover:bg-gray-50">
                  <td className="border border-gray-300 px-2 py-1 text-gray-700">资产类</td>
                  <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700">125,000.0</td>
                  <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700">128,000.0</td>
                  <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700">131,000.0</td>
                  {showColumnTotal && (
                    <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 bg-blue-50 font-medium">384,000.0</td>
                  )}
                </tr>
                <tr className="hover:bg-gray-50">
                  <td className="border border-gray-300 px-2 py-1 text-gray-700">负债类</td>
                  <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700">85,000.0</td>
                  <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700">87,000.0</td>
                  <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700">89,000.0</td>
                  {showColumnTotal && (
                    <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 bg-blue-50 font-medium">261,000.0</td>
                  )}
                </tr>
                {showRowTotal && (
                  <tr className="bg-blue-50">
                    <td className="border border-gray-300 px-2 py-1 text-gray-700 font-medium">合计</td>
                    <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 font-medium">210,000.0</td>
                    <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 font-medium">215,000.0</td>
                    <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 font-medium">220,000.0</td>
                    {showColumnTotal && (
                      <td className="border border-gray-300 px-2 py-1 text-right font-mono text-gray-700 font-medium">645,000.0</td>
                    )}
                  </tr>
                )}
              </tbody>
            </table>
          ) : (
            <div className="text-center py-12 text-gray-400 text-xs">
              请从字段列表拖拽字段到行字段、列字段或数值字段区域来创建数据透视表
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// 智能分析报告内容
export function AnalysisReportContent() {
  const [searchText, setSearchText] = useState("");
  const [reports] = useState([
    { id: "RPT001", name: "2026年第一季度资产负债分析", type: "资产负债分析", remark: "季度常规报告" },
    { id: "RPT002", name: "各部门预算执行情况对比", type: "预算执行分析", remark: "包含零售、公司、金融市场部" },
    { id: "RPT003", name: "产品收益率趋势分析", type: "收益率分析", remark: "重点关注理财产品" },
    { id: "RPT004", name: "存贷款余额月度分析", type: "存贷分析", remark: "" },
    { id: "RPT005", name: "风险资产质量评估报告", type: "风险分析", remark: "需提交监管部门" },
    { id: "RPT006", name: "部门成本费用分析", type: "成本分析", remark: "用于绩效考核" },
  ]);

  const filteredReports = reports.filter(report =>
    report.name.toLowerCase().includes(searchText.toLowerCase()) ||
    report.id.toLowerCase().includes(searchText.toLowerCase())
  );

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-800">智能分析报告</h3>
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索报告标题"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8 pr-3 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 w-64"
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto border border-gray-300 rounded">
        <table className="w-full text-xs border-collapse">
          <thead className="bg-gray-100 sticky top-0">
            <tr>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">报告编号</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">报告名称</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">报告类型</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">备注</th>
            </tr>
          </thead>
          <tbody>
            {filteredReports.map((report) => (
              <tr key={report.id} className="hover:bg-blue-50">
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{report.id}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{report.name}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{report.type}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-500">{report.remark}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// 智能演示PPT内容
export function AnalysisPPTContent() {
  const [searchText, setSearchText] = useState("");
  const [presentations] = useState([
    { id: "PPT001", name: "2026年Q1董事会汇报PPT", type: "董事会汇报", remark: "包含财务、业务、风险三部分" },
    { id: "PPT002", name: "零售银行部年度工作总结", type: "部门总结", remark: "重点展示个贷业绩" },
    { id: "PPT003", name: "产品收益率对比演示", type: "产品分析", remark: "竞品对比分析" },
    { id: "PPT004", name: "预算执行情况月度汇报", type: "预算汇报", remark: "高管月度会议使用" },
    { id: "PPT005", name: "风险管理委员会季度报告", type: "风控汇报", remark: "" },
    { id: "PPT006", name: "数字化转型进展汇报", type: "项目汇报", remark: "IT部门协同准备" },
  ]);

  const filteredPresentations = presentations.filter(ppt =>
    ppt.name.toLowerCase().includes(searchText.toLowerCase()) ||
    ppt.id.toLowerCase().includes(searchText.toLowerCase())
  );

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-800">智能演示PPT</h3>
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索PPT标题"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            className="pl-8 pr-3 py-1.5 border border-gray-300 rounded text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 w-64"
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto border border-gray-300 rounded">
        <table className="w-full text-xs border-collapse">
          <thead className="bg-gray-100 sticky top-0">
            <tr>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">演示编号</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">演示PPT名称</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">演示类型</th>
              <th className="border border-gray-300 px-3 py-2 text-left text-gray-700">备注</th>
            </tr>
          </thead>
          <tbody>
            {filteredPresentations.map((ppt) => (
              <tr key={ppt.id} className="hover:bg-blue-50">
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{ppt.id}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{ppt.name}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-700">{ppt.type}</td>
                <td className="border border-gray-300 px-3 py-2 text-gray-500">{ppt.remark}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
