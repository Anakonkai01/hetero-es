import type { ReactNode } from 'react';
import { ErrorState } from './ErrorState';
import { LoadingState } from './LoadingState';

interface QueryStateProps {
  isPending: boolean;
  isError: boolean;
  /** Cached data takes precedence over errors, so stale data stays visible. */
  hasData: boolean;
  title: string;
  children: ReactNode;
}

/** Renders loading and error states for a query; `children` render when data is ready. */
export function QueryState({ isPending, isError, hasData, title, children }: QueryStateProps) {
  if (isPending) {
    return <LoadingState />;
  }

  if (isError && !hasData) {
    return (
      <div className="card">
        <ErrorState title={title} message="The data source did not respond. Use Refresh to try again." />
      </div>
    );
  }

  return <>{children}</>;
}
