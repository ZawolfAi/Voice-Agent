import type { ReactNode } from "react";
import type { AppView } from "../../app/routes";

export type WorkspacePages = Partial<Record<AppView, ReactNode>>;

export function WorkspaceView({ view, pages }: { view: AppView; pages: WorkspacePages }) {
  return <>{pages[view] ?? pages.dashboard}</>;
}
