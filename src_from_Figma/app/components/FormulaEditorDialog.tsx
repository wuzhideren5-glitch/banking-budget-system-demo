import { useState, useRef, useEffect } from "react";
import { X, ChevronRight, ChevronDown, FileText, Database, Delete, RotateCcw, PlayCircle, ChevronsRight, ChevronsDown, ChevronUp, ChevronsUp, Search } from "lucide-react";

interface SubjectNode {
  id: string;
  code: string;
  name: string;
  type: 'report' | 'data';
  children?: SubjectNode[];
  isExpanded?: boolean;
}

interface FormulaEditorDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (formula: string) => void;
  initialFormula?: string;
  title: string;
}

export function FormulaEditorDialog({
  isOpen,
  onClose,
  onConfirm,
  initialFormula = "",
  title
}: FormulaEditorDialogProps) {
  const [formula, setFormula] = useState(initialFormula);
  const [searchText, setSearchText] = useState("");

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
  const [treeData, setTreeData] = useState<SubjectNode[]>([
    {
      id: "r1",
      code: "01",
      name: "资产类",
      type: "report",
      isExpanded: true,
      children: [
        {
          id: "r1-1",
          code: "0101",
          name: "流动资产",
          type: "report",
          isExpanded: true,
          children: [
            { id: "d1", code: "010101", name: "货币资金", type: "data" },
            { id: "d2", code: "010102", name: "交易性金融资产", type: "data" },
            { id: "d3", code: "010103", name: "应收账款", type: "data" },
          ]
        },
        {
          id: "r1-2",
          code: "0102",
          name: "非流动资产",
          type: "report",
          isExpanded: false,
          children: [
            { id: "d4", code: "010201", name: "长期股权投资", type: "data" },
            { id: "d5", code: "010202", name: "固定资产", type: "data" },
            { id: "d6", code: "010203", name: "无形资产", type: "data" },
          ]
        }
      ]
    },
    {
      id: "r2",
      code: "02",
      name: "负债类",
      type: "report",
      isExpanded: true,
      children: [
        {
          id: "r2-1",
          code: "0201",
          name: "流动负债",
          type: "report",
          isExpanded: false,
          children: [
            { id: "d7", code: "020101", name: "短期借款", type: "data" },
            { id: "d8", code: "020102", name: "应付账款", type: "data" },
          ]
        },
        {
          id: "r2-2",
          code: "0202",
          name: "非流动负债",
          type: "report",
          isExpanded: false,
          children: [
            { id: "d9", code: "020201", name: "长期借款", type: "data" },
            { id: "d10", code: "020202", name: "应付债券", type: "data" },
          ]
        }
      ]
    },
    {
      id: "r3",
      code: "03",
      name: "所有者权益类",
      type: "report",
      isExpanded: false,
      children: [
        { id: "d11", code: "030101", name: "实收资本", type: "data" },
        { id: "d12", code: "030102", name: "资本公积", type: "data" },
        { id: "d13", code: "030103", name: "盈余公积", type: "data" },
        { id: "d14", code: "030104", name: "未分配利润", type: "data" },
      ]
    }
  ]);

  const [draggedSubject, setDraggedSubject] = useState<{ code: string; name: string } | null>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string } | null>(null);
  const formulaBoxRef = useRef<HTMLTextAreaElement>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);

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

  // 全部收起
  const collapseAll = () => {
    const collapseAllNodes = (nodes: SubjectNode[]): SubjectNode[] => {
      return nodes.map(node => ({
        ...node,
        isExpanded: false,
        children: node.children ? collapseAllNodes(node.children) : undefined
      }));
    };
    setTreeData(collapseAllNodes(treeData));
    setContextMenu(null);
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

  // 添加科目到公式（在光标位置插入）
  const addSubjectToFormula = (subject: { code: string; name: string }) => {
    const textarea = formulaBoxRef.current;
    const subjectText = `<${subject.code} ${subject.name}>`;

    if (!textarea) {
      setFormula(prev => prev + subjectText);
      return;
    }

    const { selectionStart, selectionEnd } = textarea;
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

    const { selectionStart, selectionEnd } = textarea;
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

    const { selectionStart, selectionEnd } = textarea;

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
      // 模拟数据库中的科目数据
      const mockData: Record<string, number> = {
        '010101': 150000,
        '010102': 85000,
        '010103': 120000,
        '010201': 200000,
        '010202': 350000,
        '010203': 180000,
        '020101': 45000,
        '020102': 60000,
        '020201': 100000,
        '020202': 150000,
        '030101': 500000,
        '030102': 250000,
        '030103': 80000,
        '030104': 120000,
      };

      // 替换公式中的科目为数值
      let testFormula = formulaToTest;
      const subjectPattern = /<(\d+)\s+[^>]+>/g;
      let match;

      while ((match = subjectPattern.exec(formulaToTest)) !== null) {
        const subjectCode = match[1];
        const subjectValue = mockData[subjectCode];

        if (subjectValue === undefined) {
          return {
            success: false,
            message: `错误：科目代码 ${subjectCode} 在数据库中没有对应数据`
          };
        }

        testFormula = testFormula.replace(match[0], subjectValue.toString());
      }

      // 计算公式结果
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

    const { selectionStart, selectionEnd } = textarea;

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
    let currentIndex = 0;

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
    }).map(node => {
      if (node.children && node.children.length > 0) {
        return {
          ...node,
          isExpanded: true, // 搜索时自动展开
          children: filterTree(node.children, searchTerm)
        };
      }
      return node;
    });
  };

  const renderTreeNode = (node: SubjectNode, level: number = 0) => {
    const hasChildren = node.children && node.children.length > 0;
    const paddingLeft = level * 16;

    return (
      <div key={node.id}>
        <div
          className={`flex items-center gap-1 px-2 py-1.5 hover:bg-blue-50 cursor-pointer text-xs ${
            node.type === 'report' ? 'font-medium text-gray-800' : 'text-gray-700'
          }`}
          style={{ paddingLeft: `${paddingLeft + 8}px` }}
          draggable={node.type === 'data'}
          onDragStart={() => node.type === 'data' && handleDragStart({ code: node.code, name: node.name })}
          onClick={() => hasChildren && toggleNode(node.id)}
          onDoubleClick={() => node.type === 'data' && handleDoubleClick({ code: node.code, name: node.name })}
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
            <Database className="w-3 h-3 text-green-600 flex-shrink-0" />
          )}

          <span className="font-mono text-gray-600">{node.code}</span>
          <span className={node.type === 'data' ? 'cursor-move' : ''}>{node.name}</span>

          {node.type === 'data' && (
            <span className="ml-auto text-[10px] text-gray-400">可拖拽/双击</span>
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
                    onClick={() => expandToLevel(2)}
                    className="px-2 py-0.5 text-[10px] bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-100 transition-colors"
                    title="展开1级"
                  >
                    展开1级
                  </button>
                  <button
                    onClick={() => expandToLevel(3)}
                    className="px-2 py-0.5 text-[10px] bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-100 transition-colors"
                    title="展开2级"
                  >
                    展开2级
                  </button>
                  <button
                    onClick={() => expandAll()}
                    className="px-2 py-0.5 text-[10px] bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-100 transition-colors"
                    title="全部展开"
                  >
                    全部展开
                  </button>
                  <button
                    onClick={() => collapseAll()}
                    className="px-2 py-0.5 text-[10px] bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-100 transition-colors"
                    title="全部收起"
                  >
                    全部收起
                  </button>
                </div>
              </div>
              <p className="text-[10px] text-gray-500 mb-2">拖拽或双击数据科目添加到公式</p>
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
              {filterTree(treeData, searchText).map(node => renderTreeNode(node))}
            </div>
          </div>

          {/* 右侧：公式编辑区 */}
          <div className="flex-1 flex flex-col">
            {/* 公式显示区 */}
            <div className="flex-1 flex flex-col p-4">
              <h4 className="text-xs font-medium text-gray-700 mb-2">计算公式</h4>
              <div
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onClick={() => formulaBoxRef.current?.focus()}
                className="flex-1 border-2 border-dashed border-gray-300 rounded-lg bg-white overflow-hidden relative cursor-text"
              >
                {/* 底层：textarea用于接收焦点和显示光标 */}
                <textarea
                  ref={formulaBoxRef}
                  value={formula}
                  onChange={() => {}} // 受控组件需要onChange
                  onInput={handleInput}
                  onKeyDown={handleKeyDown}
                  onCopy={(e) => e.preventDefault()}
                  onCut={(e) => e.preventDefault()}
                  onPaste={(e) => e.preventDefault()}
                  placeholder="拖拽左侧科目到此处，或使用下方按钮编辑公式&#10;例如: <010101 货币资金> + <010102 交易性金融资产> * ( <010103 应收账款> - <020101 短期借款> )"
                  className="absolute inset-0 w-full h-full p-4 font-mono text-sm resize-none bg-transparent border-none outline-none focus:outline-none cursor-text selection:bg-blue-200"
                  style={{
                    color: 'rgba(0, 0, 0, 0.01)',
                    caretColor: '#1f2937',
                    WebkitTextFillColor: 'rgba(0, 0, 0, 0.01)'
                  }}
                />

                {/* 顶层：语法高亮显示层 */}
                <div className="absolute inset-0 w-full h-full p-4 font-mono text-sm pointer-events-none overflow-auto">
                  {formula ? (
                    <div className="whitespace-pre-wrap break-all leading-normal">
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
                      className="px-3 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors text-sm font-medium"
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
                      className={`px-3 py-2 text-white rounded transition-colors text-sm font-medium ${btn.color}`}
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
          <div className="flex items-center justify-between">
            <div className="flex-1 text-xs text-gray-600">
              {formula ? (
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-700">公式转译结果:</span>
                  <span className="font-mono bg-white px-3 py-1 rounded border border-gray-300 text-gray-800">
                    {getTranslatedFormula()}
                  </span>
                </div>
              ) : (
                <span className="text-gray-400">公式为空</span>
              )}
            </div>
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
