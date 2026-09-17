import type { HTMLAttributes } from "react";
import { cx } from "./cx";

export function Text({ tone, className, ...props }: HTMLAttributes<HTMLParagraphElement> & { tone?: "ok" | "bad" }) {
  return <p className={cx("ui-text", tone, className)} {...props} />;
}
