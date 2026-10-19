import { useProduct } from '@heteroes/product-ui';
import { Link } from 'react-router';

interface ObjectNotFoundProps {
  backTo: string;
  backLabel: string;
}

export function ObjectNotFound({ backTo, backLabel }: ObjectNotFoundProps) {
  const { t } = useProduct();
  return (
    <div className="card">
      <div className="empty">
        <b>{t('Object not found')}</b>
        <span>{t('This object does not exist or has been removed from the data source.')}</span>
        <span className="acts">
          <Link className="btn pri" to={backTo}>
            {backLabel}
          </Link>
          <Link className="btn" to="/dashboard">
            {t('Back to Dashboard')}
          </Link>
        </span>
      </div>
    </div>
  );
}
