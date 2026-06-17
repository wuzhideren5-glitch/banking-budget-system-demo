import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";

const STORAGE_PREFIX = "table-column-widths:v1:";

export type UseTableColumnWidthsOptions = {
  minWidth?: number;
  maxWidth?: number;
};

/**
 * 表格列宽拖拽调节；按 columnKey 持久化到 localStorage。
 * colWidth(key, defaultPx) 返回当前像素宽度（含默认值）。
 */
export function useTableColumnWidths(tableId: string, options?: UseTableColumnWidthsOptions) {
  const minWidth = options?.minWidth ?? 48;
  const maxWidth = options?.maxWidth ?? 640;
  const storageKey = `${STORAGE_PREFIX}${tableId}`;

  const [widths, setWidths] = useState<Record<string, number>>(() => {
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
      localStorage.setItem(storageKey, JSON.stringify(widths));
    } catch {
      /* ignore quota */
    }
  }, [storageKey, widths]);

  const beginColumnResize = useCallback(
    (colKey: string, e: React.MouseEvent, defaultPx: number, getThEl?: () => HTMLElement | null) => {
      e.preventDefault();
      e.stopPropagation();
      const th = getThEl?.() ?? (e.currentTarget as HTMLElement).closest("th");
      const rect = th?.getBoundingClientRect();
      const startW = widths[colKey] ?? rect?.width ?? defaultPx;
      const startX = e.clientX;

      const onMove = (ev: MouseEvent) => {
        const next = Math.round(
          Math.min(maxWidth, Math.max(minWidth, startW + (ev.clientX - startX))),
        );
        setWidths((prev) => ({ ...prev, [colKey]: next }));
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.removeProperty("cursor");
        document.body.style.removeProperty("user-select");
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      document.body.style.cursor = "ew-resize";
      document.body.style.userSelect = "none";
    },
    [widths, maxWidth, minWidth],
  );

  const colWidth = useCallback(
    (colKey: string, defaultPx: number): number => {
      return widths[colKey] ?? defaultPx;
    },
    [widths],
  );

  /** 仅当存在自定义宽度时返回 style，便于与行高等其它 style 合并 */
  const colStyle = useCallback(
    (colKey: string, defaultPx: number): CSSProperties => {
      const w = widths[colKey] ?? defaultPx;
      return { width: w, minWidth: w, boxSizing: "border-box" };
    },
    [widths],
  );

  return { colWidth, colStyle, beginColumnResize, widths };
}
