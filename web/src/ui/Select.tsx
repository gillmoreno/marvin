import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";
import { cx } from "./cx";

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cx("ui-select", className)} {...props} />;
}

export function Check({
  label,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className={cx("ui-check", className)}>
      <input type="checkbox" {...props} />
      <span>{label}</span>
    </label>
  );
}
