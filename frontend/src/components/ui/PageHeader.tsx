import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, description, meta, actions }: PageHeaderProps) {
  return (
    <div className="ph">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
        {meta}
      </div>
      {actions && <div className="acts">{actions}</div>}
    </div>
  );
}

/** Detail page header: title, then a row of badges, IDs and copy buttons. */
export function PageHeaderMeta({ children }: { children: ReactNode }) {
  return (
    <p
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '6px 12px',
        alignItems: 'center',
        marginTop: 10,
      }}
    >
      {children}
    </p>
  );
}
