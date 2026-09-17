import type { ReactNode } from "react";
import { cx } from "./cx";

export function Field({ label, wide, children }: { label: string; wide?: boolean; children: ReactNode }) {
  return (
    <label className={cx("ui-field", wide && "wide")}>
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Fields({ children }: { children: ReactNode }) {
  return <div className="ui-fields">{children}</div>;
}
