import { useState } from 'react';
import { Link } from 'react-router';
import { useProduct } from '@heteroes/product-ui';
import { useSession } from '../../app/session';

export function AccountMenu() {
  const { t } = useProduct();
  const { session, signOut } = useSession();
  const [error, setError] = useState('');
  if (!session) return null;
  return (
    <div className="account-control">
      <details
        className="account-menu"
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
        }}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.currentTarget.open = false;
            event.currentTarget.querySelector('summary')?.focus();
          }
        }}
      >
        <summary aria-label={t('Account menu')} title={session.user.displayName}>
          <span className="account-avatar">{session.user.displayName.slice(0, 1).toUpperCase()}</span>
          <span className="account-name">{session.user.displayName}</span>
          <span aria-hidden="true">⌄</span>
        </summary>
        <nav aria-label={t('Account menu')}>
          <b>{session.user.displayName}</b>
          <Link
            to="/profile"
            onClick={(event) => {
              event.currentTarget.closest('details')!.open = false;
            }}
          >
            {t('Profile')}
          </Link>
          <Link
            to="/profile#security"
            onClick={(event) => {
              event.currentTarget.closest('details')!.open = false;
            }}
          >
            {t('Security')}
          </Link>
          <button
            type="button"
            onClick={() =>
              void signOut().catch((cause: unknown) =>
                setError(cause instanceof Error ? cause.message : t('Could not sign out.')),
              )
            }
          >
            {t('Sign out')}
          </button>
        </nav>
      </details>
      {error && (
        <span role="alert" className="note err">
          {error}
        </span>
      )}
    </div>
  );
}
