export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="empty-state error-state" role="alert"><strong>{message}</strong>{onRetry && <button className="outline-btn" onClick={onRetry}>Retry</button>}</div>;
}