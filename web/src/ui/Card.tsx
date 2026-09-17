import { Children, cloneElement, isValidElement, type HTMLAttributes, type ReactElement, type ReactNode } from "react";
import { cx } from "./cx";
import { LockMark, LockReason } from "./Lock";

export function Card({
  className,
  locked = false,
  lockReason,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { locked?: boolean; lockReason?: ReactNode }) {
  const items = Children.toArray(children);
  const title = items[0];
  const rest = items.slice(1);
  const headed =
    locked && isValidElement(title) && title.type === "h3"
      ? cloneElement(title as ReactElement<{ children?: ReactNode }>, undefined, <>{(title as ReactElement<{ children?: ReactNode }>).props.children} <LockMark /></>)
      : title;
  return (
    <div className={cx("ui-card", locked && "is-locked", className)} {...props}>
      {headed}
      {locked && <LockReason>{lockReason}</LockReason>}
      {locked ? <div className="ui-locked" inert>{rest}</div> : rest}
    </div>
  );
}

export function Block({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="ui-block">
      {title && <h4>{title}</h4>}
      {children}
    </div>
  );
}
