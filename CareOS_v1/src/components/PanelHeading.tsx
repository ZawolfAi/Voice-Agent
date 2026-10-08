import type { ReactNode } from "react";

export function PanelHeading({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="panel-heading">
      <div><h2>{title}</h2><p>{detail}</p></div>
      {action}
    </div>
  );
}
