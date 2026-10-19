import { useProduct } from '@heteroes/product-ui';
import { Navigate, Outlet } from 'react-router';
import { useSession } from '../../app/session';
import { LoadingState } from '../common/LoadingState';

export function RequireSession() {
  const { t } = useProduct();
  const { session, pending, unavailable, refreshSession } = useSession();
  if (pending)
    return (
      <div className="app auth-screen">
        <LoadingState />
      </div>
    );
  if (unavailable && !session)
    return (
      <div className="app auth-screen">
        <div className="card cb">
          <p>{t('Could not verify the session.')}</p>
          <button className="btn" onClick={() => void refreshSession()}>
            {t('Retry')}
          </button>
        </div>
      </div>
    );
  return session ? <Outlet /> : <Navigate to="/login" replace />;
}
