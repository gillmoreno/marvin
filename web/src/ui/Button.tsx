import type { ButtonHTMLAttributes } from "react";
import { cx } from "./cx";

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  return <button type="button" className={cx("ui-btn", variant !== "primary" && variant, className)} {...props} />;
}
