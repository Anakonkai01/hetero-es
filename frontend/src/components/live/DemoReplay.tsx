import { useProduct } from '@heteroes/product-ui';
import { useDemoTimeline } from '../../hooks/useDemoTimeline';
import { RunLiveView } from './RunLiveView';

/** A real, finished run of this project's lab, replayed in a loop. Public: it holds no names, only GPU labels and timings. */
export function DemoReplay({ fallback }: { fallback: React.ReactNode }) {
  const { t } = useProduct();
  const demo = useDemoTimeline();
  if (!demo.data) return <>{fallback}</>;
  return (
    <div className="demo-replay">
      <div className="demo-replay-head">
        <span>
          <span className="live-dot" aria-hidden="true" /> {t('A real run from this lab, replayed')}
        </span>
        <small className="hint">{t('3 different GPUs · 36 candidates · 3 generations')}</small>
      </div>
      <RunLiveView timeline={demo.data} mode="replay" variant="hero" title={t('A real run from this lab, replayed')} />
    </div>
  );
}
