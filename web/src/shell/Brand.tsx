import { CollapseIcon, ExpandIcon } from "../icons";

export type EnterpriseMark = { ee: boolean; company: string | null } | null | undefined;

export function Brand({
  ee,
  collapsed,
  onToggle,
}: {
  ee?: EnterpriseMark;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const company = ee?.ee ? (ee.company ?? "Enterprise") : null;
  return (
    <div className={`join-brand${ee?.ee ? " ee" : ""}`}>
      <div className="join-brand-row">
        <span className="join-brand-mark"><i /></span>
        <b>Marvin</b>
        <button
          type="button"
          className="rail-toggle"
          aria-expanded={!collapsed}
          aria-controls="marvin-rail"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={onToggle}
        >
          {collapsed ? <ExpandIcon /> : <CollapseIcon />}
          <span className="rail-label">{collapsed ? "Expand sidebar" : "Collapse sidebar"}</span>
        </button>
      </div>
      {company && <em className="ee-mark">{company}</em>}
    </div>
  );
}
