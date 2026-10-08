export type AppView =
  | "dashboard" | "patients" | "assistant" | "notes" | "documents"
  | "appointments" | "portal" | "analytics" | "messages" | "departments"
  | "reports" | "settings" | "account" | "integrations" | "teamAudit";

export const appPath = (view: AppView): string => `#app/${view}`;

export function navigateToView(view: AppView): void {
  window.history.pushState({}, "", appPath(view));
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function viewFromLocation(): AppView {
  const value = window.location.hash.replace(/^#app\/?/, "");
  const allowed: AppView[] = ["dashboard", "patients", "assistant", "notes", "documents", "appointments", "portal", "analytics", "messages", "departments", "reports", "settings", "account", "integrations", "teamAudit"];
  return allowed.includes(value as AppView) ? value as AppView : "dashboard";
}