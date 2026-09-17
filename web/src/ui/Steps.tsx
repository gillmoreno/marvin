import type { ReactNode } from "react";

export function Steps({ items }: { items: { title?: string; detail: ReactNode }[] }) {
  return (
    <ol className="ui-steps">
      {items.map((item, index) => (
        <li key={item.title ?? index}>
          {item.title && <b>{item.title}</b>}
          <span>{item.detail}</span>
        </li>
      ))}
    </ol>
  );
}
