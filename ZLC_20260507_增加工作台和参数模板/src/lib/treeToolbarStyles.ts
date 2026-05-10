/**
 * 树形面板「收起本级 / 展开下级 / … / 全部收起 / 全部展开」工具条按钮统一样式。
 * 与报告科目、部门科目维护等页面保持一致（灰底描边，不用高亮蓝区分「全部展开」）。
 */
export const treeToolbarButtonClass =
  "flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded transition-colors text-gray-800";

/** 弹窗内较密排版（公式编辑器、产品选择器等） */
export const treeToolbarButtonCompactClass =
  "px-2 py-0.5 text-[10px] bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded transition-colors text-gray-800";
