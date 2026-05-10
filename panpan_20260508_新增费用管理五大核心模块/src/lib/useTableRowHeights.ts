import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";

const STORAGE_PREFIX = "table-row-heights:v1:";

export type UseTableRowHeightsOptions = {
  minHeight?: number;
  maxHeight?: number;
};

/**
 * 为表格/列表行提供类似 Excel 的纵向拖拽调行高能力；高度按 rowKey 持久化到 localStorage。
 */
export function useTableRowHeights(tableId: string, options?: UseTableRowHeightsOptions) {
  const minHeight = options?.minHeight ?? 22;
  const maxHeight = options?.maxHeight ?? 240;
  const storageKey = `${STORAGE_PREFIX}${tableId}`;

  const [heights, setHeights] = useState<Record<string, number>>(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return {};
      const parsed = JSON.parse(raw) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, number>;
      }
    } catch {
      /* ignore */
    }
    return {};
  });

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(heights));
    } catch {
      /* ignore quota */
    }
  }, [storageKey, heights]);

  const beginResize = useCallback(
    (rowKey: string, e: React.MouseEvent, getRowEl?: () => HTMLElement | null) => {
      e.preventDefault();
      e.stopPropagation();
      const rowEl = getRowEl?.() ?? (e.currentTarget as HTMLElement).closest("tr");
      const rect = rowEl?.getBoundingClientRect();
      const startH = heights[rowKey] ?? rect?.height ?? 28;
      const startY = e.clientY;

      const onMove = (ev: MouseEvent) => {
        const next = Math.round(
          Math.min(maxHeight, Math.max(minHeight, startH + (ev.clientY - startY))),
        );
        setHeights((prev) => ({ ...prev, [rowKey]: next }));
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.removeProperty("cursor");
        document.body.style.removeProperty("user-select");
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      document.body.style.cursor = "ns-resize";
      document.body.style.userSelect = "none";
    },
    [heights, maxHeight, minHeight],
  );

  const rowStyle = useCallback(
    (rowKey: string): CSSProperties => {
      const h = heights[rowKey];
      if (h === undefined) return {};
      return { height: h, boxSizing: "border-box" };
    },
    [heights],
  );

  return { rowStyle, beginResize, heights };
}
