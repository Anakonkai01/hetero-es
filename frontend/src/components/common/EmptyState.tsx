import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  message?: string;
  children?: ReactNode;
}

export function EmptyState({ title, message, children }: EmptyStateProps) {
  return (
    <div className="empty">
      <b>{title}</b>
      {message && <span>{message}</span>}
      {children}
    </div>
  );
}
