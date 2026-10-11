import {useProduct} from '@heteroes/product-ui';
function Skeleton({ height, width }: { height: number; width?: number }) {
  return <div className="skel" style={{ height, width }} />;
}

/** Page-level skeleton shown while the first data is loading. */
export function LoadingState() {
  const {t}=useProduct();
  return (
    <div
      aria-busy="true"
      aria-label={t("Loading")}
      style={{ display: "flex", flexDirection: "column", gap: 18 }}
    >
      <Skeleton height={30} width={280} />

      <div className="stats">
        {[0, 1, 2].map((index) => (
          <div className="stat" key={index}>
            <Skeleton height={14} width={120} />
            <Skeleton height={30} width={60} />
          </div>
        ))}
      </div>

      <div className="card">
        <div className="ch">
          <Skeleton height={16} width={180} />
        </div>
        <div
          className="cb"
          style={{ display: "flex", flexDirection: "column", gap: 12 }}
        >
          {[0, 1, 2, 3].map((index) => (
            <Skeleton height={18} key={index} />
          ))}
        </div>
      </div>
    </div>
  );
}
