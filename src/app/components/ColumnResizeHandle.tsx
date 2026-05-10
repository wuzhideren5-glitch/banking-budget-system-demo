/**
 * 放在表头 th 右侧，父级需 position:relative。
 */
export function ColumnResizeHandle({
  onResizeStart,
}: {
  onResizeStart: (e: React.MouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      title="拖动调整列宽"
      className="absolute right-0 top-0 bottom-0 w-1.5 z-[2] cursor-ew-resize hover:bg-blue-400/50"
      onMouseDown={onResizeStart}
    />
  );
}
