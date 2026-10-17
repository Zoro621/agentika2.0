import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

export default function VirtualList<T>({
  items,
  rowHeight,
  height,
  renderRow,
  itemKey,
  label,
  className = "",
}: {
  items: T[];
  rowHeight: number;
  height: number;
  renderRow: (item: T) => ReactNode;
  itemKey: (item: T) => string | number;
  label: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = 0;
    setTop(0);
  }, [items.length, label]);
  const first = Math.max(0, Math.floor(top / rowHeight) - 5);
  const last = Math.min(
    items.length,
    Math.ceil((top + height) / rowHeight) + 5,
  );
  return (
    <div
      ref={ref}
      className={`virtual-list ${className}`}
      role="list"
      aria-label={label}
      tabIndex={0}
      style={{
        height: Math.min(height, Math.max(rowHeight, items.length * rowHeight)),
        overflow: "auto",
        position: "relative",
      }}
      onScroll={(e) => setTop(e.currentTarget.scrollTop)}
    >
      <div style={{ height: items.length * rowHeight, position: "relative" }}>
        {items.slice(first, last).map((item, index) => (
          <div
            key={itemKey(item)}
            role="listitem"
            aria-setsize={items.length}
            aria-posinset={first + index + 1}
            className="virtual-row"
            style={{
              position: "absolute",
              top: (first + index) * rowHeight,
              height: rowHeight,
              left: 0,
              right: 0,
            }}
          >
            {renderRow(item)}
          </div>
        ))}
      </div>
      {!items.length && <p className="virtual-empty">No matching items.</p>}
    </div>
  );
}
