import {useProduct} from '@heteroes/product-ui';
import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  message?: string;
  children?: ReactNode;
}

export function EmptyState({ title, message, children }: EmptyStateProps) {
  const {t}=useProduct();
  return (
    <div className="empty">
      <b>{title}</b>
      {message && <span>{t(message)}</span>}
      {children}
    </div>
  );
}
