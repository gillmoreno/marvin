import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "./cx";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("ui-card", className)} {...props} />;
}

export function Block({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="ui-block">
      {title && <h4>{title}</h4>}
      {children}
    </div>
  );
}
