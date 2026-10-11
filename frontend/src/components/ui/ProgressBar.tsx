import {useProduct} from '@heteroes/product-ui';
import { percent } from "../../lib/format";

interface ProgressBarProps {
  done: number;
  total: number;
  large?: boolean;
}

export function ProgressBar({ done, total, large }: ProgressBarProps) {
  const {t}=useProduct();
  return (
    <div
      className="bar"
      role="progressbar"
      aria-label={t('Progress')}
      aria-valuemin={0}
      aria-valuemax={Math.max(1,total)}
      aria-valuenow={Math.min(Math.max(0,done),Math.max(1,total))}
      style={large ? { height: 8, borderRadius: 4 } : undefined}
    >
      <div className="fill" style={{ width: `${percent(done, total)}%` }} />
    </div>
  );
}
