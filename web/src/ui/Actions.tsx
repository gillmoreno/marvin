import type { HTMLAttributes } from "react";
import { cx } from "./cx";

export function Actions({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("ui-actions", className)} {...props} />;
}
