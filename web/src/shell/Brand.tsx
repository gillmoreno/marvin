import { CollapseIcon, ExpandIcon } from "../icons";

export type EnterpriseMark = { ee: boolean; company: string | null } | null | undefined;

export function BrandLogo({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <img
      className={collapsed ? "join-brand-mark-img" : "join-brand-lockup-img"}
      src={collapsed ? "/marvin-mark.svg" : "/marvin-lockup.svg"}
      alt="Marvin"
      draggable={false}
    />
  );
}

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
        <BrandLogo collapsed={collapsed} />
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
