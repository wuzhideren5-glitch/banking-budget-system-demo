import type { CSSProperties, MouseEvent, ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "./utils";

export type FinancialGridRowKind = "normal" | "summary" | "muted" | "readonly" | "locked" | "error";

export type FinancialGridColumn<T> = {
  id: string;
  header: ReactNode;
  groupId?: string;
  minWidth?: number;
  width?: number;
  align?: "left" | "center" | "right";
  hiddenWhenGroupCollapsed?: boolean;
  className?: string;
  headerClassName?: string;
  render: (row: T) => ReactNode;
};

export type FinancialGridColumnGroup = {
  id: string;
  header: ReactNode;
  collapsedHeader?: ReactNode;
  collapsible?: boolean;
  colSpanWhenCollapsed?: number;
};

export type FinancialGridProps<T> = {
  rows: T[];
  columns: FinancialGridColumn<T>[];
  columnGroups?: FinancialGridColumnGroup[];
  expandedColumnGroups?: Record<string, boolean>;
  onToggleColumnGroup?: (groupId: string) => void;
  getRowId: (row: T) => string;
  getRowLabel: (row: T) => ReactNode;
  getRowLevel?: (row: T) => number;
  getRowKind?: (row: T) => FinancialGridRowKind;
  getRowHasChildren?: (row: T) => boolean;
  isRowExpanded?: (row: T) => boolean;
  onToggleRow?: (row: T) => void;
  onRowClick?: (row: T) => void;
  onRowContextMenu?: (event: MouseEvent<HTMLTableRowElement>, row: T) => void;
  getRowClassName?: (row: T) => string | undefined;
  primaryHeader?: ReactNode;
  emptyMessage?: ReactNode;
  className?: string;
  tableClassName?: string;
  primaryColumnWidth?: number;
};

function alignClass(align?: FinancialGridColumn<unknown>["align"]) {
  if (align === "right") return "text-right";
  if (align === "center") return "text-center";
  return "text-left";
}

function rowKindClass(kind: FinancialGridRowKind) {
  if (kind === "summary") return "bg-[#fbfcfe] font-semibold text-[var(--bb-text-strong)]";
  if (kind === "muted" || kind === "readonly") return "bg-[#fafbfc] text-[var(--bb-text-muted)]";
  if (kind === "locked") return "bb-cell-locked";
  if (kind === "error") return "bb-cell-error";
  return "bg-white text-[var(--bb-text)]";
}

function isGroupExpanded(groupId: string | undefined, expandedColumnGroups?: Record<string, boolean>) {
  if (!groupId) return true;
  return expandedColumnGroups?.[groupId] ?? false;
}

export function ReportGrid<T>({
  rows,
  columns,
  columnGroups = [],
  expandedColumnGroups,
  onToggleColumnGroup,
  getRowId,
  getRowLabel,
  getRowLevel = () => 1,
  getRowKind = () => "normal",
  getRowHasChildren = () => false,
  isRowExpanded = () => false,
  onToggleRow,
  onRowClick,
  onRowContextMenu,
  getRowClassName,
  primaryHeader = "项目",
  emptyMessage = "暂无可展示数据。",
  className,
  tableClassName,
  primaryColumnWidth = 260,
}: FinancialGridProps<T>) {
  const visibleColumns = columns.filter((column) => {
    if (!column.groupId) return true;
    if (!column.hiddenWhenGroupCollapsed) return true;
    return isGroupExpanded(column.groupId, expandedColumnGroups);
  });
  const hasGroups = columnGroups.length > 0;

  const groupedHeaderCells = columnGroups
    .map((group) => {
      const groupColumns = visibleColumns.filter((column) => column.groupId === group.id);
      if (groupColumns.length === 0) return null;
      const expanded = isGroupExpanded(group.id, expandedColumnGroups);
      const span = expanded ? groupColumns.length : group.colSpanWhenCollapsed ?? groupColumns.length;
      return (
        <th key={group.id} colSpan={span} className="border-b border-r border-[var(--bb-border)] px-2 py-1.5 text-center">
          {group.collapsible ? (
            <button
              type="button"
              className="inline-flex items-center gap-1 font-semibold text-[var(--bb-text-strong)] hover:text-[var(--bb-primary)]"
              onClick={() => onToggleColumnGroup?.(group.id)}
            >
              {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              {expanded ? group.header : group.collapsedHeader ?? group.header}
            </button>
          ) : (
            group.header
          )}
        </th>
      );
    })
    .filter(Boolean);

  const ungroupedHeaderCells = visibleColumns.filter((column) => !column.groupId);

  return (
    <div className={cn("bb-table-wrap", className)}>
      <table className={cn("bb-table bb-table-dense min-w-full", tableClassName)}>
        <thead>
          {hasGroups ? (
            <tr>
              <th
                rowSpan={2}
                className="sticky left-0 z-30 border-r border-[var(--bb-border)] bg-[var(--bb-bg-subtle)] px-2 py-1.5 text-left"
                style={{ minWidth: primaryColumnWidth, width: primaryColumnWidth }}
              >
                {primaryHeader}
              </th>
              {ungroupedHeaderCells.map((column) => (
                <th
                  key={column.id}
                  rowSpan={2}
                  className={cn("border-b border-r border-[var(--bb-border)] px-2 py-1.5", alignClass(column.align), column.headerClassName)}
                  style={columnStyle(column)}
                >
                  {column.header}
                </th>
              ))}
              {groupedHeaderCells}
            </tr>
          ) : null}
          <tr>
            {!hasGroups ? (
              <th
                className="sticky left-0 z-30 border-r border-[var(--bb-border)] bg-[var(--bb-bg-subtle)] px-2 py-1.5 text-left"
                style={{ minWidth: primaryColumnWidth, width: primaryColumnWidth }}
              >
                {primaryHeader}
              </th>
            ) : null}
            {visibleColumns
              .filter((column) => !hasGroups || column.groupId)
              .map((column) => (
                <th
                  key={column.id}
                  className={cn("border-r border-[var(--bb-border-soft)] px-2 py-1.5", alignClass(column.align), column.headerClassName)}
                  style={columnStyle(column)}
                >
                  {column.header}
                </th>
              ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={1 + visibleColumns.length} className="px-3 py-8 text-center text-[var(--bb-text-muted)]">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const rowId = getRowId(row);
              const level = Math.max(1, getRowLevel(row));
              const kind = getRowKind(row);
              const hasChildren = getRowHasChildren(row);
              const expanded = isRowExpanded(row);
              return (
                <tr
                  key={rowId}
                  className={cn(rowKindClass(kind), onRowClick ? "cursor-pointer" : "", getRowClassName?.(row))}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onContextMenu={onRowContextMenu ? (event) => onRowContextMenu(event, row) : undefined}
                >
                  <td
                    className="sticky left-0 z-10 border-r border-[var(--bb-border)] bg-inherit px-2 py-1 text-[var(--bb-text-strong)]"
                    style={{ minWidth: primaryColumnWidth, width: primaryColumnWidth, paddingLeft: 8 + (level - 1) * 16 }}
                  >
                    <span className="inline-flex min-w-0 items-center gap-1">
                      <button
                        type="button"
                        onClick={() => onToggleRow?.(row)}
                        disabled={!hasChildren}
                        className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm text-[var(--bb-text-muted)] hover:bg-[var(--bb-bg-muted)] disabled:opacity-0"
                        title={expanded ? "收起" : "展开"}
                      >
                        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      </button>
                      <span className="truncate">{getRowLabel(row)}</span>
                    </span>
                  </td>
                  {visibleColumns.map((column) => (
                    <td
                      key={`${rowId}-${column.id}`}
                      className={cn(
                        "border-r border-[var(--bb-border-soft)] px-2 py-1",
                        alignClass(column.align),
                        column.align === "right" ? "bb-cell-number" : "",
                        column.className,
                      )}
                      style={columnStyle(column)}
                    >
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

function columnStyle<T>(column: FinancialGridColumn<T>): CSSProperties {
  return {
    minWidth: column.minWidth,
    width: column.width,
  };
}

export function EditableFinancialGrid<T>(props: FinancialGridProps<T>) {
  return <ReportGrid {...props} tableClassName={cn("bb-editable-financial-grid", props.tableClassName)} />;
}

export function GridToolbar({ className, ...props }: { className?: string; children: ReactNode }) {
  return <div className={cn("bb-toolbar", className)} {...props} />;
}
