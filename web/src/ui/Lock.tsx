import type { ReactNode } from "react";

/** Gold lock on an Enterprise-only control. The emoji stays visible; the body goes inert. */
export function LockMark() {
  return <span className="ui-lock-mark" title="Enterprise">🔒</span>;
}

export function LockReason({ children }: { children?: ReactNode }) {
  return (
    <p className="ui-lock-reason">
      {children ?? (
        <>
          Needs an Enterprise license. <a href="/settings/license">Paste one</a>.
        </>
      )}
    </p>
  );
}

export function Lock({
  on,
  reason,
  children,
}: {
  on: boolean;
  reason?: ReactNode;
  children: ReactNode;
}) {
  if (!on) return children;
  return (
    <div className="ui-lock-wrap">
      <LockReason>{reason}</LockReason>
      <div className="ui-locked" inert>
        {children}
      </div>
    </div>
  );
}
