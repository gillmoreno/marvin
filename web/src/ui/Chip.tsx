import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "./cx";

export function Chips({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="ui-chips" role="tablist" aria-label={label}>
      {children}
    </div>
  );
}

export function Chip({
  selected,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean }) {
  return <button type="button" role="tab" aria-selected={selected} className={cx("ui-chip", selected && "on", className)} {...props} />;
}
