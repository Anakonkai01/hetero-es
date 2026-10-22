import { useProduct } from '@heteroes/product-ui';

export function Pagination({
  page,
  total,
  pageSize = 10,
  onChange,
}: {
  page: number;
  total: number;
  pageSize?: number;
  onChange: (page: number) => void;
}) {
  const { t } = useProduct();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav className="pagination" aria-label={t('Pagination')}>
      <span className="hint">
        {total ? (page - 1) * pageSize + 1 : 0}–{Math.min(total, page * pageSize)} / {total}
      </span>
      <div className="acts">
        <button className="btn" type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          {t('Previous')}
        </button>
        <span>
          {page} / {pages}
        </span>
        <button className="btn" type="button" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          {t('Next')}
        </button>
      </div>
    </nav>
  );
}
