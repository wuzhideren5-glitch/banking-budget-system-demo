/**
 * 放在行容器（首列 td 或树形行 div）底部，需父级 position:relative。
 */
export function TableRowResizeHandle({
  onResizeStart,
}: {
  onResizeStart: (e: React.MouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      role="separator"
      aria-orientation="horizontal"
      title="拖动调整行高"
      className="absolute left-0 right-0 bottom-0 h-1.5 z-[1] cursor-ns-resize hover:bg-blue-400/40"
      onMouseDown={onResizeStart}
    />
  );
}
