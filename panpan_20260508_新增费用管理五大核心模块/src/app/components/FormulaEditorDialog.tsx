import { useState, useRef, useEffect } from "react";
import { X, ChevronRight, ChevronDown, FileText, Database, Delete, RotateCcw, PlayCircle, ChevronsRight, ChevronsDown, ChevronUp, ChevronsUp, Search } from "lucide-react";
import { apiGet, type DataAccountDto, type ReportAccountDto, type ReportDataMappingDto } from "@/lib/api";
import { treeToolbarButtonCompactClass } from "@/lib/treeToolbarStyles";

interface SubjectNode {
  id: string;
  code: string;
  name: string;
  type: 'report' | 'data';
  appliesToAllProducts?: boolean;
  children?: SubjectNode[];
  isExpanded?: boolean;
}

interface FormulaEditorDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (formula: string) => void;
  initialFormula?: string;
  title: string;
  currentDataSubject?: string;
  currentAppliesToAllProducts?: boolean;
  formulaType?: "budget" | "actual";
}

export function FormulaEditorDialog({
  isOpen,
  onClose,
  onConfirm,
  initialFormula = "",
  title,
  currentDataSubject = "",
  currentAppliesToAllProducts = false,
  formulaType = "budget",
}: FormulaEditorDialogProps) {
  const [formula, setFormula] = useState(initialFormula);
  const [searchText, setSearchText] = useState("");
  const [loadingTree, setLoadingTree] = useState(false);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [availableDataCodes, setAvailableDataCodes] = useState<Set<string>>(new Set());
  const [dataAppliesToAllByCode, setDataAppliesToAllByCode] = useState<Map<string, boolean>>(new Map());
  const [treeData, setTreeData] = useState<SubjectNode[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const [draggedSubject, setDraggedSubject] = useState<{ code: string; name: string } | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string } | null>(null);
  const formulaBoxRef = useRef<HTMLTextAreaElement>(null);
  const highlightLayerRef = useRef<HTMLDivElement>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);

  // 当对话框打开时，重新加载初始公式并聚焦
  useEffect(() => {
    if (isOpen) {
      setFormula(initialFormula);
      setSearchText("");
      // 延迟聚焦，确保DOM已渲染
      setTimeout(() => {
        if (formulaBoxRef.current) {
          formulaBoxRef.current.focus();
          // 将光标移到末尾
          const length = initialFormula.length;
          formulaBoxRef.current.setSelectionRange(length, length);
        }
      }, 100);
    }
  }, [isOpen, initialFormula]);

  /** 有搜索关键词时展开整棵科目树，便于命中节点可见（与 DataReport 行为一致） */
  useEffect(() => {
    if (!searchText.trim()) return;
    setTreeData((prev) => {
      const expandAllNodes = (nodes: SubjectNode[]): SubjectNode[] =>
        nodes.map((node) => ({
          ...node,
          isExpanded: true,
          children: node.children ? expandAllNodes(node.children) : undefined,
        }));
      return expandAllNodes(prev);
    });
  }, [searchText]);

  const buildSubjectTree = (
    reports: ReportAccountDto[],
    mappings: ReportDataMappingDto[],
    dataAccounts: DataAccountDto[]
  ): SubjectNode[] => {
    const reportMap = new Map<string, SubjectNode>();
    reports.forEach((r) => {
      reportMap.set(r.report_acct_code, {
        id: `report-${r.report_acct_code}`,
        code: r.report_acct_code,
        name: r.report_acct_name,
        type: "report",
        children: [],
        isExpanded: r.level <= 2,
      });
    });

    const dataMap = new Map<string, DataAccountDto>();
    dataAccounts.forEach((d) => dataMap.set(d.data_acct_code, d));

    mappings.forEach((m) => {
      const parent = reportMap.get(m.report_acct_code);
      const data = dataMap.get(m.data_acct_code);
      if (!parent || !data) return;
      parent.children = parent.children ?? [];
      parent.children.push({
        id: `data-${m.report_acct_code}-${data.data_acct_code}`,
        code: data.data_acct_code,
        name: data.data_acct_name,
        type: "data",
        appliesToAllProducts: Number(data.applies_to_all_products ?? 0) === 1,
      });
    });

    const roots: SubjectNode[] = [];
    reports.forEach((r) => {
      const current = reportMap.get(r.report_acct_code);
      if (!current) return;
      if (r.parent_code && reportMap.has(r.parent_code)) {
        const parent = reportMap.get(r.parent_code)!;
        parent.children = parent.children ?? [];
        parent.children.push(current);
      } else {
        roots.push(current);
      }
    });

    const sortTree = (nodes: SubjectNode[]) => {
      nodes.sort((a, b) => a.code.localeCompare(b.code, "zh-CN"));
      nodes.forEach((n) => n.children && sortTree(n.children));
    };
    sortTree(roots);
    return roots;
  };

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setLoadingTree(true);
    setTreeError(null);
    void (async () => {
      try {
        const [reports, mappings, dataAccounts] = await Promise.all([
          apiGet<ReportAccountDto[]>("/api/report-accounts"),
          apiGet<ReportDataMappingDto[]>("/api/report-data-mappings"),
          apiGet<DataAccountDto[]>("/api/data-accounts"),
        ]);
        if (cancelled) return;
        setTreeData(buildSubjectTree(reports, mappings, dataAccounts));
        setAvailableDataCodes(new Set(dataAccounts.map((d) => d.data_acct_code)));
        setDataAppliesToAllByCode(
          new Map(
            dataAccounts.map((d) => [
              d.data_acct_code,
              Number(d.applies_to_all_products ?? 0) === 1,
            ])
          )
        );
      } catch (e) {
        if (cancelled) return;
        setTreeError(e instanceof Error ? e.message : "加载科目树失败");
        setTreeData([]);
        setAvailableDataCodes(new Set());
        setDataAppliesToAllByCode(new Map());
      } finally {
        if (!cancelled) setLoadingTree(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, formulaType]);

  // 关闭右键菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    };

    if (contextMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [contextMenu]);

  if (!isOpen) return null;

  const toggleNode = (nodeId: string) => {
    const toggleInTree = (nodes: SubjectNode[]): SubjectNode[] => {
      return nodes.map(node => {
        if (node.id === nodeId) {
          return { ...node, isExpanded: !node.isExpanded };
        }
        if (node.children) {
          return { ...node, children: toggleInTree(node.children) };
        }
        return node;
      });
    };
    setTreeData(toggleInTree(treeData));
  };

  const findDepthById = (nodes: SubjectNode[], nodeId: string, depth = 1): number | null => {
    for (const node of nodes) {
      if (node.id === nodeId) return depth;
      if (node.children) {
        const found = findDepthById(node.children, nodeId, depth + 1);
        if (found != null) return found;
      }
    }
    return null;
  };

  const collectIdsAtDepth = (nodes: SubjectNode[], targetDepth: number, depth = 1, out: string[] = []): string[] => {
    nodes.forEach((node) => {
      if (node.children && node.children.length > 0 && depth === targetDepth) {
        out.push(node.id);
      }
      if (node.children) collectIdsAtDepth(node.children, targetDepth, depth + 1, out);
    });
    return out;
  };

  const collectSubtreeExpandableIds = (nodes: SubjectNode[], nodeId: string): string[] => {
    let ids: string[] = [];
    const walk = (node: SubjectNode) => {
      if (node.children && node.children.length > 0) ids.push(node.id);
      node.children?.forEach(walk);
    };
    const findAndWalk = (list: SubjectNode[]) => {
      list.forEach((n) => {
        if (n.id === nodeId) {
          walk(n);
          return;
        }
        if (n.children) findAndWalk(n.children);
      });
    };
    findAndWalk(nodes);
    return ids;
  };

  const setExpandedForIds = (ids: string[], expanded: boolean) => {
    const walk = (nodes: SubjectNode[]): SubjectNode[] =>
      nodes.map((node) => {
        if (ids.includes(node.id)) {
          return { ...node, isExpanded: expanded };
        }
        if (node.children) return { ...node, children: walk(node.children) };
        return node;
      });
    setTreeData((prev) => walk(prev));
  };

  const collapseCurrentLevelOnly = () => {
    if (selectedNodeId) {
      setExpandedForIds([selectedNodeId], false);
      return;
    }
    setExpandedForIds(collectIdsAtDepth(treeData, 1), false);
  };

  const expandNextLevelOnly = () => {
    if (selectedNodeId) {
      setExpandedForIds([selectedNodeId], true);
      return;
    }
    setExpandedForIds(collectIdsAtDepth(treeData, 1), true);
  };

  const collapseAllCurrentLevel = () => {
    const level = selectedNodeId ? (findDepthById(treeData, selectedNodeId) ?? 1) : 1;
    setExpandedForIds(collectIdsAtDepth(treeData, level), false);
  };

  const expandAllChildren = () => {
    if (selectedNodeId) {
      setExpandedForIds(collectSubtreeExpandableIds(treeData, selectedNodeId), true);
      return;
    }
    expandAll();
  };

  // 展开到指定层级
  const expandToLevel = (level: number) => {
    const expandNodes = (nodes: SubjectNode[], currentLevel: number = 1): SubjectNode[] => {
      return nodes.map(node => {
        if (node.children) {
          return {
            ...node,
            isExpanded: currentLevel < level,
            children: expandNodes(node.children, currentLevel + 1)
          };
        }
        return node;
      });
    };
    setTreeData(expandNodes(treeData));
    setContextMenu(null);
  };

  // 展开指定节点的所有子节点
  const expandNodeChildren = (nodeId: string) => {
    const expandChildren = (nodes: SubjectNode[]): SubjectNode[] => {
      return nodes.map(node => {
        if (node.id === nodeId && node.children) {
          const expandAllChildren = (children: SubjectNode[]): SubjectNode[] => {
            return children.map(child => ({
              ...child,
              isExpanded: true,
              children: child.children ? expandAllChildren(child.children) : undefined
            }));
          };
          return { ...node, isExpanded: true, children: expandAllChildren(node.children) };
        }
        if (node.children) {
          return { ...node, children: expandChildren(node.children) };
        }
        return node;
      });
    };
    setTreeData(expandChildren(treeData));
    setContextMenu(null);
  };

  // 全部展开
  const expandAll = () => {
    const expandAllNodes = (nodes: SubjectNode[]): SubjectNode[] => {
      return nodes.map(node => ({
        ...node,
        isExpanded: true,
        children: node.children ? expandAllNodes(node.children) : undefined
      }));
    };
    setTreeData(expandAllNodes(treeData));
    setContextMenu(null);
  };

  // 收起指定节点
  const collapseNode = (nodeId: string) => {
    const collapseInTree = (nodes: SubjectNode[]): SubjectNode[] => {
      return nodes.map(node => {
        if (node.id === nodeId) {
          return { ...node, isExpanded: false };
        }
        if (node.children) {
          return { ...node, children: collapseInTree(node.children) };
        }
        return node;
      });
    };
    setTreeData(collapseInTree(treeData));
    setContextMenu(null);
  };

  // 全部收起（清空搜索，避免过滤层强制展开；与选中节点无关）
  const collapseAll = () => {
    setSearchText("");
    setTreeData((prev) => {
      const collapseAllNodes = (nodes: SubjectNode[]): SubjectNode[] =>
        nodes.map((node) => ({
          ...node,
          isExpanded: false,
          children: node.children ? collapseAllNodes(node.children) : undefined,
        }));
      return collapseAllNodes(prev);
    });
    setContextMenu(null);
  };

  const getSubjectRanges = (text: string): Array<{ start: number; end: number }> => {
    const ranges: Array<{ start: number; end: number }> = [];
    const pattern = /<[^>]+>/g;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(text)) !== null) {
      ranges.push({ start: match.index, end: match.index + match[0].length });
    }
    return ranges;
  };

  const normalizeSelectionRange = (
    text: string,
    rawStart: number,
    rawEnd: number
  ): { start: number; end: number } => {
    let start = Math.max(0, Math.min(rawStart, text.length));
    let end = Math.max(0, Math.min(rawEnd, text.length));
    if (start > end) [start, end] = [end, start];
    const ranges = getSubjectRanges(text);

    if (start === end) {
      for (const r of ranges) {
        if (start > r.start && start < r.end) {
          const leftDist = start - r.start;
          const rightDist = r.end - start;
          const snap = leftDist <= rightDist ? r.start : r.end;
          return { start: snap, end: snap };
        }
      }
      return { start, end };
    }

    for (const r of ranges) {
      if (start > r.start && start < r.end) start = r.start;
      if (end > r.start && end < r.end) end = r.end;
    }
    return { start, end };
  };

  const normalizeCaretInTextarea = () => {
    const textarea = formulaBoxRef.current;
    if (!textarea) return;
    const { start, end } = normalizeSelectionRange(
      formula,
      textarea.selectionStart,
      textarea.selectionEnd
    );
    if (start !== textarea.selectionStart || end !== textarea.selectionEnd) {
      textarea.setSelectionRange(start, end);
    }
  };

  const handleDragStart = (subject: { code: string; name: string }) => {
    setDraggedSubject(subject);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (draggedSubject) {
      // 获取拖放位置对应的光标位置
      const textarea = formulaBoxRef.current;
      if (textarea) {
        textarea.focus();
        // 简单地添加到末尾（更精确的实现需要计算鼠标位置对应的字符位置）
      }
      addSubjectToFormula(draggedSubject);
      setDraggedSubject(null);
    }
  };

  const handleFormulaScroll = () => {
    const textarea = formulaBoxRef.current;
    const layer = highlightLayerRef.current;
    if (!textarea || !layer) return;
    layer.scrollTop = textarea.scrollTop;
    layer.scrollLeft = textarea.scrollLeft;
  };

  // 添加科目到公式（在光标位置插入）
  const addSubjectToFormula = (subject: { code: string; name: string }) => {
    const textarea = formulaBoxRef.current;
    const subjectText = `<${subject.code} ${subject.name}>`;

    if (!textarea) {
      setFormula(prev => prev + subjectText);
      return;
    }

    const { start: selectionStart, end: selectionEnd } = normalizeSelectionRange(
      formula,
      textarea.selectionStart,
      textarea.selectionEnd
    );
    const newFormula = formula.slice(0, selectionStart) + subjectText + formula.slice(selectionEnd);
    setFormula(newFormula);

    // 设置光标位置到插入内容之后
    setTimeout(() => {
      const newCursorPos = selectionStart + subjectText.length;
      textarea.focus();
      textarea.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  };

  // 双击添加科目
  const handleDoubleClick = (subject: { code: string; name: string }) => {
    addSubjectToFormula(subject);
  };

  // 右键菜单
  const handleContextMenu = (e: React.MouseEvent, nodeId: string) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, nodeId });
  };

  const handleButtonClick = (value: string) => {
    const textarea = formulaBoxRef.current;
    if (!textarea) {
      setFormula(prev => prev + value);
      return;
    }

    const { start: selectionStart, end: selectionEnd } = normalizeSelectionRange(
      formula,
      textarea.selectionStart,
      textarea.selectionEnd
    );
    const newFormula = formula.slice(0, selectionStart) + value + formula.slice(selectionEnd);
    setFormula(newFormula);

    // 设置光标位置到插入内容之后
    setTimeout(() => {
      const newCursorPos = selectionStart + value.length;
      textarea.focus();
      textarea.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  };

  const handleBackspace = () => {
    const textarea = formulaBoxRef.current;
    if (!textarea) return;

    const { start: selectionStart, end: selectionEnd } = normalizeSelectionRange(
      formula,
      textarea.selectionStart,
      textarea.selectionEnd
    );

    if (selectionStart === 0 && selectionEnd === 0) return; // 光标在最开始，无法删除

    if (selectionStart !== selectionEnd) {
      // 有选中内容，删除选中部分
      const newFormula = formula.slice(0, selectionStart) + formula.slice(selectionEnd);
      setFormula(newFormula);
      setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(selectionStart, selectionStart);
      }, 0);
      return;
    }

    // 检查光标前一个字符是否是 '>'
    if (formula[selectionStart - 1] === '>') {
      // 找到对应的 '<' 位置
      const openBracket = formula.lastIndexOf('<', selectionStart - 2);
      if (openBracket !== -1) {
        // 删除整个 <...> 部分
        const newFormula = formula.slice(0, openBracket) + formula.slice(selectionStart);
        setFormula(newFormula);
        setTimeout(() => {
          textarea.focus();
          textarea.setSelectionRange(openBracket, openBracket);
        }, 0);
        return;
      }
    }

    // 否则删除光标前一个字符
    const newFormula = formula.slice(0, selectionStart - 1) + formula.slice(selectionStart);
    setFormula(newFormula);
    setTimeout(() => {
      textarea.focus();
      textarea.setSelectionRange(selectionStart - 1, selectionStart - 1);
    }, 0);
  };

  const handleClear = () => {
    if (formula.length === 0) return;

    // 使用自定义对话框，默认按钮是取消
    const userChoice = confirm('确定要清空整个公式吗？\n\n点击"确定"清空，点击"取消"保留');
    if (userChoice) {
      setFormula("");
      // 清空后聚焦到文本框
      setTimeout(() => {
        if (formulaBoxRef.current) {
          formulaBoxRef.current.focus();
        }
      }, 0);
    }
  };

  // 验证公式的核心函数
  const validateFormula = (formulaToTest: string): { success: boolean; message?: string; result?: number; translatedFormula?: string } => {
    if (!formulaToTest) {
      return { success: false, message: '公式为空，无法验证' };
    }

    try {
      // 替换公式中的科目为数值
      let testFormula = formulaToTest;
      testFormula = testFormula.replace(/\b(sum|avg|max|min)\s*\(/gi, (m) => `${m.toUpperCase().replace(/\s+/g, "")}`);
      const subjectPattern = /<([A-Z]\d+)\s+[^>]+>/g;
      let match;
      let replacementSeed = 1;

      while ((match = subjectPattern.exec(formulaToTest)) !== null) {
        const subjectCode = match[1];
        if (!availableDataCodes.has(subjectCode)) {
          return {
            success: false,
            message: `错误：科目代码 ${subjectCode} 在系统数据科目中不存在`
          };
        }
        if (currentAppliesToAllProducts && !dataAppliesToAllByCode.get(subjectCode)) {
          return {
            success: false,
            message: `错误：适用所有产品科目的公式仅可引用“适用所有产品科目”。当前引用 ${subjectCode} 不满足约束。`,
          };
        }
        // 验证阶段仅关注公式结构与科目有效性，数值使用占位符即可
        testFormula = testFormula.replace(match[0], String(replacementSeed));
        replacementSeed += 1;
      }

      // 计算公式结果
      const SUM = (...args: number[]) => args.reduce((acc, cur) => acc + cur, 0);
      const AVG = (...args: number[]) => (args.length === 0 ? 0 : SUM(...args) / args.length);
      const MAX = (...args: number[]) => (args.length === 0 ? 0 : Math.max(...args));
      const MIN = (...args: number[]) => (args.length === 0 ? 0 : Math.min(...args));
      // eslint-disable-next-line no-eval
      const result = eval(testFormula);

      return {
        success: true,
        result,
        translatedFormula: testFormula
      };
    } catch (error) {
      return {
        success: false,
        message: `公式语法错误！\n\n${error instanceof Error ? error.message : '请检查公式语法是否正确'}`
      };
    }
  };

  const handleTestFormula = () => {
    const validation = validateFormula(formula);

    if (validation.success) {
      alert(`公式测试成功！\n\n原始公式:\n${formula}\n\n替换后:\n${validation.translatedFormula}\n\n计算结果: ${validation.result!.toLocaleString('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`);
    } else {
      alert(validation.message);
    }
  };

  const handleConfirm = () => {
    // 保存前先验证公式
    if (formula) {
      const validation = validateFormula(formula);

      if (!validation.success) {
        alert(`公式验证失败，无法保存！\n\n${validation.message}`);
        return;
      }
    }

    // 验证通过，保存公式
    onConfirm(formula);
    onClose();
  };

  // 处理键盘事件，让数据科目作为整体，阻止直接输入
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const textarea = formulaBoxRef.current;
    if (!textarea) return;

    const normalized = normalizeSelectionRange(formula, textarea.selectionStart, textarea.selectionEnd);
    if (normalized.start !== textarea.selectionStart || normalized.end !== textarea.selectionEnd) {
      textarea.setSelectionRange(normalized.start, normalized.end);
    }
    const { start: selectionStart, end: selectionEnd } = normalized;

    // 允许的导航和选择键
    const allowedKeys = [
      'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown',
      'Home', 'End', 'PageUp', 'PageDown',
      'Tab', 'Escape'
    ];

    // 允许复制选择（虽然我们阻止了复制事件，但这里允许Ctrl+A选择全部）
    if (e.key === 'a' && (e.ctrlKey || e.metaKey)) {
      return; // 允许全选
    }

    // 阻止所有可打印字符和编辑操作
    if (!allowedKeys.includes(e.key) && e.key.length === 1) {
      e.preventDefault();
      return;
    }

    // 阻止空格、回车等
    if (e.key === ' ' || e.key === 'Enter' || e.key === 'Backspace' || e.key === 'Delete') {
      e.preventDefault();
      return;
    }

    // 处理左箭头键
    if (e.key === 'ArrowLeft' && selectionStart === selectionEnd) {
      // 检查光标前面是否是 '>'，如果是，跳过整个 <...>
      if (selectionStart > 0 && formula[selectionStart - 1] === '>') {
        const openBracket = formula.lastIndexOf('<', selectionStart - 2);
        if (openBracket !== -1) {
          e.preventDefault();
          textarea.setSelectionRange(openBracket, openBracket);
        }
      }
    }

    // 处理右箭头键
    if (e.key === 'ArrowRight' && selectionStart === selectionEnd) {
      // 检查光标后面是否是 '<'，如果是，跳过整个 <...>
      if (selectionStart < formula.length && formula[selectionStart] === '<') {
        const closeBracket = formula.indexOf('>', selectionStart + 1);
        if (closeBracket !== -1) {
          e.preventDefault();
          textarea.setSelectionRange(closeBracket + 1, closeBracket + 1);
        }
      }
    }

    if (allowedKeys.includes(e.key)) {
      setTimeout(() => {
        normalizeCaretInTextarea();
      }, 0);
    }
  };

  // 阻止直接输入
  const handleInput = (e: React.FormEvent<HTMLTextAreaElement>) => {
    e.preventDefault();
    // 恢复到之前的值
    if (formulaBoxRef.current) {
      formulaBoxRef.current.value = formula;
    }
  };

  // 获取公式转译结果（用于底部状态栏显示）
  const getTranslatedFormula = () => {
    if (!formula) return "";

    const validation = validateFormula(formula);

    if (validation.success) {
      return validation.translatedFormula || "";
    } else {
      return "公式错误";
    }
  };

  // 语法高亮渲染函数
  const renderHighlightedFormula = (text: string) => {
    if (!text) return null;

    const parts: JSX.Element[] = [];
    let lastIndex = 0;
    const subjectPattern = /<[^>]+>/g;
    let match;

    while ((match = subjectPattern.exec(text)) !== null) {
      // 添加科目前的文本
      if (match.index > lastIndex) {
        const beforeText = text.slice(lastIndex, match.index);
        parts.push(...parseNonSubjectText(beforeText, parts.length));
      }

      // 添加科目（紫红色）
      parts.push(
        <span key={parts.length} className="text-pink-700 font-semibold">
          {match[0]}
        </span>
      );

      lastIndex = match.index + match[0].length;
    }

    // 添加剩余文本
    if (lastIndex < text.length) {
      const remainingText = text.slice(lastIndex);
      parts.push(...parseNonSubjectText(remainingText, parts.length));
    }

    return parts;
  };

  // 解析非科目文本（数字用蓝色，运算符用绿色）
  const parseNonSubjectText = (text: string, startKey: number) => {
    const parts: JSX.Element[] = [];

    for (let i = 0; i < text.length; i++) {
      const char = text[i];

      if (/\d/.test(char) || char === '.') {
        // 数字（蓝色）
        let numberEnd = i;
        while (numberEnd < text.length && (/\d/.test(text[numberEnd]) || text[numberEnd] === '.')) {
          numberEnd++;
        }
        parts.push(
          <span key={startKey + parts.length} className="text-blue-600 font-medium">
            {text.slice(i, numberEnd)}
          </span>
        );
        i = numberEnd - 1;
      } else if (/[+\-*/()=<>]/.test(char) || ['SUM', 'AVG', 'MAX', 'MIN'].some(fn => text.slice(i).startsWith(fn))) {
        // 运算符和函数（绿色）
        let opEnd = i + 1;
        if (['SUM', 'AVG', 'MAX', 'MIN'].some(fn => text.slice(i).startsWith(fn))) {
          const fn = ['SUM', 'AVG', 'MAX', 'MIN'].find(fn => text.slice(i).startsWith(fn));
          opEnd = i + (fn?.length || 0);
        }
        parts.push(
          <span key={startKey + parts.length} className="text-green-600 font-medium">
            {text.slice(i, opEnd)}
          </span>
        );
        i = opEnd - 1;
      } else {
        // 空格等其他字符
        parts.push(
          <span key={startKey + parts.length} className="text-gray-800">
            {char}
          </span>
        );
      }
    }

    return parts;
  };

  // 搜索过滤函数
  const filterTree = (nodes: SubjectNode[], searchTerm: string): SubjectNode[] => {
    if (!searchTerm) return nodes;

    const searchLower = searchTerm.toLowerCase();

    return nodes.filter(node => {
      const matchesCurrent =
        node.code.toLowerCase().includes(searchLower) ||
        node.name.toLowerCase().includes(searchLower);

      if (node.children && node.children.length > 0) {
        const filteredChildren = filterTree(node.children, searchTerm);
        if (filteredChildren.length > 0) {
          return true;
        }
      }

      return matchesCurrent;
    }).map((node) => {
      if (node.children && node.children.length > 0) {
        return {
          ...node,
          children: filterTree(node.children, searchTerm),
        };
      }
      return node;
    });
  };

  const renderTreeNode = (node: SubjectNode, level: number = 0) => {
    const hasChildren = node.children && node.children.length > 0;
    const paddingLeft = level * 16;
    const dataNodeBlocked =
      node.type === "data" &&
      currentAppliesToAllProducts &&
      !node.appliesToAllProducts;

    return (
      <div key={node.id}>
        <div
          className={`flex items-center gap-1 px-2 py-1.5 cursor-pointer text-xs ${
            selectedNodeId === node.id ? "bg-blue-100" : "hover:bg-blue-50"
          } ${
            node.type === "report"
              ? "font-medium text-gray-800"
              : dataNodeBlocked
                ? "text-gray-400 bg-gray-50"
                : "text-gray-700"
          }`}
          style={{ paddingLeft: `${paddingLeft + 8}px` }}
          draggable={node.type === 'data' && !dataNodeBlocked}
          onDragStart={() => node.type === 'data' && !dataNodeBlocked && handleDragStart({ code: node.code, name: node.name })}
          onClick={() => hasChildren && toggleNode(node.id)}
          onMouseDown={() => setSelectedNodeId(node.id)}
          onDoubleClick={() => node.type === 'data' && !dataNodeBlocked && handleDoubleClick({ code: node.code, name: node.name })}
          onContextMenu={(e) => handleContextMenu(e, node.id)}
        >
          {hasChildren ? (
            node.isExpanded ? (
              <ChevronDown className="w-3 h-3 text-gray-500 flex-shrink-0" />
            ) : (
              <ChevronRight className="w-3 h-3 text-gray-500 flex-shrink-0" />
            )
          ) : (
            <span className="w-3" />
          )}

          {node.type === 'report' ? (
            <FileText className="w-3 h-3 text-blue-600 flex-shrink-0" />
          ) : (
            <Database className={`w-3 h-3 flex-shrink-0 ${dataNodeBlocked ? "text-gray-400" : "text-green-600"}`} />
          )}

          <span className="font-mono text-gray-600">{node.code}</span>
          <span className={node.type === 'data' && !dataNodeBlocked ? 'cursor-move' : ''}>{node.name}</span>

          {node.type === 'data' && (
            <span className="ml-auto text-[10px] text-gray-400">
              {dataNodeBlocked ? "不在可引用范围" : "可拖拽/双击"}
            </span>
          )}
        </div>

        {hasChildren && node.isExpanded && (
          <div>
            {node.children?.map(child => renderTreeNode(child, level + 1))}
          </div>
        )}
      </div>
    );
  };

  const operatorButtons = [
    { label: '+', value: '+', color: 'bg-orange-500 hover:bg-orange-600' },
    { label: '-', value: '-', color: 'bg-orange-500 hover:bg-orange-600' },
    { label: '×', value: '*', color: 'bg-orange-500 hover:bg-orange-600' },
    { label: '÷', value: '/', color: 'bg-orange-500 hover:bg-orange-600' },
    { label: ',', value: ',', color: 'bg-purple-500 hover:bg-purple-600' },
    { label: '(', value: '(', color: 'bg-purple-500 hover:bg-purple-600' },
    { label: ')', value: ')', color: 'bg-purple-500 hover:bg-purple-600' },
  ];

  const numberButtons = ['7', '8', '9', '4', '5', '6', '1', '2', '3', '0', '.'];

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-[90vw] h-[80vh] flex flex-col">
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-medium text-gray-800">{title}</h3>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
          >
            <X className="w-4 h-4 text-gray-600" />
          </button>
        </div>

        {/* 主体内容 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 左侧：科目树 */}
          <div className="w-[40%] border-r border-gray-200 flex flex-col">
            <div className="px-3 py-2 bg-gray-100 border-b border-gray-200">
              <div className="flex items-center justify-between mb-1">
                <h4 className="text-xs font-medium text-gray-700">科目列表</h4>
                <div className="flex flex-wrap gap-1">
                  <button
                    type="button"
                    onClick={collapseCurrentLevelOnly}
                    className={treeToolbarButtonCompactClass}
                    title="收起本级"
                  >
                    收起本级
                  </button>
                  <button
                    type="button"
                    onClick={expandNextLevelOnly}
                    className={treeToolbarButtonCompactClass}
                    title="展开下级"
                  >
                    展开下级
                  </button>
                  <button
                    type="button"
                    onClick={collapseAllCurrentLevel}
                    className={treeToolbarButtonCompactClass}
                    title="收起全部本级"
                  >
                    收起全部本级
                  </button>
                  <button
                    type="button"
                    onClick={expandAllChildren}
                    className={treeToolbarButtonCompactClass}
                    title="展开全部下级"
                  >
                    展开全部下级
                  </button>
                  <button
                    type="button"
                    onClick={() => collapseAll()}
                    className={treeToolbarButtonCompactClass}
                    title="全部收起"
                  >
                    全部收起
                  </button>
                  <button
                    type="button"
                    onClick={() => expandAll()}
                    className={treeToolbarButtonCompactClass}
                    title="全部展开"
                  >
                    全部展开
                  </button>
                </div>
              </div>
              <p className="text-[10px] text-gray-500 mb-2">
                {currentAppliesToAllProducts
                  ? "当前为适用所有产品科目：仅可引用“适用所有产品科目”（灰色项不可选）"
                  : "拖拽或双击数据科目添加到公式"}
              </p>
              <div className="relative">
                <Search className="w-3 h-3 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="搜索科目..."
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  className="w-full pl-8 pr-8 py-1 text-[10px] border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                {searchText && (
                  <button
                    onClick={() => setSearchText("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-200 rounded transition-colors"
                    title="清除搜索"
                  >
                    <X className="w-3 h-3 text-gray-500" />
                  </button>
                )}
              </div>
            </div>
            <div className="flex-1 overflow-auto">
              {loadingTree ? (
                <div className="px-3 py-2 text-xs text-gray-500">正在加载数据库科目树...</div>
              ) : treeError ? (
                <div className="px-3 py-2 text-xs text-red-600">科目树加载失败：{treeError}</div>
              ) : (
                filterTree(treeData, searchText).map(node => renderTreeNode(node))
              )}
            </div>
          </div>

          {/* 右侧：公式编辑区 */}
          <div className="flex-1 flex flex-col">
            {/* 公式显示区 */}
            <div className="flex-1 flex flex-col p-4">
              <div className="mb-2">
                <h4 className="text-xs font-medium text-gray-700">计算公式</h4>
                <p className="mt-1 text-xs text-gray-600">
                  <span className="font-mono text-gray-800">{currentDataSubject || "-"}</span>
                  <span className="ml-1">=</span>
                </p>
              </div>
              <div
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                className="flex-1 border-2 border-dashed border-gray-300 rounded-lg bg-white overflow-hidden relative cursor-text"
              >
                {/* 底层：textarea用于接收焦点和显示光标 */}
                <textarea
                  ref={formulaBoxRef}
                  value={formula}
                  onChange={() => {}} // 受控组件需要onChange
                  onInput={handleInput}
                  onKeyDown={handleKeyDown}
                  onSelect={() => normalizeCaretInTextarea()}
                  onScroll={handleFormulaScroll}
                  onCopy={(e) => e.preventDefault()}
                  onCut={(e) => e.preventDefault()}
                  onPaste={(e) => e.preventDefault()}
                  placeholder="拖拽左侧科目到此处，或使用下方按钮编辑公式&#10;例如: <010101 货币资金> + <010102 交易性金融资产> * ( <010103 应收账款> - <020101 短期借款> )"
                  className="absolute inset-0 w-full h-full p-4 font-mono text-sm leading-6 resize-none bg-transparent border-none outline-none focus:outline-none cursor-text selection:bg-blue-200"
                  style={{
                    color: 'rgba(0, 0, 0, 0.01)',
                    caretColor: '#1f2937',
                    WebkitTextFillColor: 'rgba(0, 0, 0, 0.01)'
                  }}
                />

                {/* 顶层：语法高亮显示层 */}
                <div
                  ref={highlightLayerRef}
                  className="absolute inset-0 w-full h-full p-4 font-mono text-sm leading-6 pointer-events-none overflow-auto"
                >
                  {formula ? (
                    <div className="whitespace-pre-wrap break-words">
                      {renderHighlightedFormula(formula)}
                    </div>
                  ) : (
                    <div className="text-gray-400 text-xs">
                      <p>拖拽左侧科目到此处，或使用下方按钮编辑公式</p>
                      <p className="mt-2">例如: <span className="text-pink-700 font-semibold">&lt;010101 货币资金&gt;</span> <span className="text-green-600">+</span> <span className="text-pink-700 font-semibold">&lt;010102 交易性金融资产&gt;</span> <span className="text-green-600">*</span> <span className="text-green-600">(</span> <span className="text-pink-700 font-semibold">&lt;010103 应收账款&gt;</span> <span className="text-green-600">-</span> <span className="text-pink-700 font-semibold">&lt;020101 短期借款&gt;</span> <span className="text-green-600">)</span></p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 按钮区 */}
            <div className="border-t border-gray-200 p-4 bg-gray-50">
              <h4 className="text-xs font-medium text-gray-700 mb-2">输入面板</h4>

              <div className="grid grid-cols-12 gap-2">
                {/* 数字按钮区 */}
                <div className="col-span-6 grid grid-cols-3 gap-2">
                  {numberButtons.map(num => (
                    <button
                      key={num}
                      onClick={() => handleButtonClick(num)}
                      className="px-3 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors text-base font-medium"
                    >
                      {num}
                    </button>
                  ))}
                </div>

                {/* 运算符和括号按钮区 */}
                <div className="col-span-4 grid grid-cols-2 gap-2">
                  {operatorButtons.map(btn => (
                    <button
                      key={btn.value}
                      onClick={() => handleButtonClick(btn.value)}
                      className={`px-3 py-2 text-white rounded transition-colors text-base font-medium ${btn.color}`}
                    >
                      {btn.label}
                    </button>
                  ))}
                </div>

                {/* 功能按钮区 */}
                <div className="col-span-2 flex flex-col gap-2">
                  <button
                    onClick={handleBackspace}
                    className="flex items-center justify-center gap-1 px-3 py-2 bg-red-500 text-white rounded hover:bg-red-600 transition-colors text-xs"
                    title="退格"
                  >
                    <Delete className="w-3 h-3" />
                    退格
                  </button>
                  <button
                    onClick={handleClear}
                    className="flex items-center justify-center gap-1 px-3 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors text-xs"
                    title="清空"
                  >
                    <RotateCcw className="w-3 h-3" />
                    清空
                  </button>
                  <button
                    onClick={handleTestFormula}
                    className="flex items-center justify-center gap-1 px-3 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors text-xs"
                    title="测试公式"
                  >
                    <PlayCircle className="w-3 h-3" />
                    测试
                  </button>
                </div>
              </div>

              {/* 常用函数按钮 */}
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => handleButtonClick('SUM(')}
                  className="px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 transition-colors text-xs"
                >
                  SUM()
                </button>
                <button
                  onClick={() => handleButtonClick('AVG(')}
                  className="px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 transition-colors text-xs"
                >
                  AVG()
                </button>
                <button
                  onClick={() => handleButtonClick('MAX(')}
                  className="px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 transition-colors text-xs"
                >
                  MAX()
                </button>
                <button
                  onClick={() => handleButtonClick('MIN(')}
                  className="px-3 py-1.5 bg-green-600 text-white rounded hover:bg-green-700 transition-colors text-xs"
                >
                  MIN()
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 底部状态栏 */}
        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center justify-end">
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="px-4 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleConfirm}
                className="px-4 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                确认
              </button>
            </div>
          </div>
        </div>

        {/* 右键菜单 */}
        {contextMenu && (
          <div
            ref={contextMenuRef}
            className="fixed bg-white border border-gray-300 rounded shadow-lg py-1 z-50 min-w-[140px]"
            style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}
          >
            <button
              onClick={() => expandToLevel(2)}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-blue-50 flex items-center gap-2"
            >
              <ChevronsRight className="w-3 h-3" />
              展开1级
            </button>
            <button
              onClick={() => expandToLevel(3)}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-blue-50 flex items-center gap-2"
            >
              <ChevronsRight className="w-3 h-3" />
              展开2级
            </button>
            <button
              onClick={() => expandNodeChildren(contextMenu.nodeId)}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-blue-50 flex items-center gap-2"
            >
              <ChevronsDown className="w-3 h-3" />
              展开下级
            </button>
            <button
              onClick={() => expandAll()}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-green-50 flex items-center gap-2"
            >
              <ChevronsDown className="w-3 h-3" />
              全部展开
            </button>
            <div className="border-t border-gray-200 my-1"></div>
            <button
              onClick={() => collapseNode(contextMenu.nodeId)}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-orange-50 flex items-center gap-2"
            >
              <ChevronUp className="w-3 h-3" />
              收起本级
            </button>
            <button
              onClick={() => collapseAll()}
              className="w-full px-3 py-1.5 text-xs text-left hover:bg-red-50 flex items-center gap-2"
            >
              <ChevronsUp className="w-3 h-3" />
              全部收起
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
