import type { ReactNode } from 'react';

interface ErrorStateProps {
  title: string;
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
  children?: ReactNode;
}

export function ErrorState({ title, message, onRetry, retryLabel = 'Retry', children }: ErrorStateProps) {
  return (
    <div className="empty" role="alert">
      <b>{title}</b>
      {message && <span>{message}</span>}
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          {retryLabel}
        </button>
      )}
      {children}
    </div>
  );
}
