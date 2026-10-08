export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return <div className="empty-state loading-state" role="status" aria-live="polite"><span className="loading-bar" /><span>{label}</span></div>;
}