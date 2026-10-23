import { useProduct } from '@heteroes/product-ui';
import type { Generation } from '../../types/generation';
import { EmptyState } from '../common/EmptyState';

const LEFT = 48;
const WIDTH = 576;
const TOP = 12;
const HEIGHT = 212;

function linePath(points: [number, number][]): string {
  if (points.length === 1) {
    const [x, y] = points[0];
    return `M${x.toFixed(1)} ${y.toFixed(1)} L${x.toFixed(1)} ${y.toFixed(1)}`;
  }

  return points.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
}

export function RewardChart({ generations }: { generations: Generation[] }) {
  const { t } = useProduct();
  const maxReward = Math.max(0.6, ...generations.flatMap((g) => [g.rewardMean ?? 0, g.rewardBest ?? 0]));
  const count = generations.length || 1;
  const labelEvery = Math.max(1, Math.ceil(count / 8));
  const x = (index: number) => LEFT + ((index + 0.5) * WIDTH) / count;
  const y = (value: number) => TOP + (1 - value / maxReward) * HEIGHT;

  const pointsOf = (key: 'rewardMean' | 'rewardBest') =>
    generations.flatMap((generation, index): [number, number][] => {
      const value = generation[key];
      return value === undefined ? [] : [[x(index), y(value)]];
    });

  const meanPoints = pointsOf('rewardMean');

  if (meanPoints.length === 0) {
    return (
      <EmptyState
        title={t('No reward data yet')}
        message="Reward appears once the first generation has an accepted candidate."
      />
    );
  }

  const gridLines = [12, 82.7, 153.3];

  return (
    <>
      <div className="hint" style={{ marginBottom: 6 }}>
        {t('Vertical axis: reward (score, scale 0 –')}
        {maxReward.toFixed(2)}
        {t('). Horizontal axis: generations in order of creation.')}
      </div>

      <svg
        viewBox="0 0 640 264"
        className="reward-chart"
        width="100%"
        role="img"
        aria-label={t('Chart of mean and best reward per generation')}
        style={{ display: 'block' }}
      >
        <defs>
          <marker id="mA" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5">
            <circle cx="5" cy="5" r="4" fill="var(--acc)" />
          </marker>
          <marker id="mB" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5">
            <rect x="1" y="1" width="8" height="8" fill="var(--chart-secondary)" />
          </marker>
        </defs>

        {gridLines.map((line) => (
          <line key={line} x1="48" y1={line} x2="624" y2={line} stroke="var(--line2)" />
        ))}
        <line x1="48" y1="224" x2="624" y2="224" stroke="var(--line)" />

        {[
          [maxReward.toFixed(2), 16],
          [((maxReward * 2) / 3).toFixed(2), 86.7],
          [(maxReward / 3).toFixed(2), 157.3],
          ['0', 228],
        ].map(([label, ty]) => (
          <text key={label} x="40" y={ty} textAnchor="end" fontSize="11" fill="var(--mut)">
            {label}
          </text>
        ))}

        <path
          d={linePath(pointsOf('rewardBest'))}
          fill="none"
          stroke="var(--chart-secondary)"
          strokeWidth="1.75"
          strokeDasharray="6 4"
          markerStart="url(#mB)"
          markerMid={count <= 30 ? 'url(#mB)' : undefined}
          markerEnd="url(#mB)"
        />
        <path
          d={linePath(meanPoints)}
          fill="none"
          stroke="var(--acc)"
          strokeWidth="2.5"
          markerStart="url(#mA)"
          markerMid={count <= 30 ? 'url(#mA)' : undefined}
          markerEnd="url(#mA)"
        />
        <g className="reward-axis">
          {generations.map(
            (generation, index) =>
              (index % labelEvery === 0 || index === generations.length - 1) && (
                <text
                  key={generation.generationId}
                  x={x(index)}
                  y={248}
                  textAnchor="middle"
                  fontSize="10"
                  fill="var(--mut)"
                >
                  #{Number(generation.generationId.split('.g').at(-1) ?? index) + 1}
                </text>
              ),
          )}
        </g>
      </svg>

      <div className="legendl">
        <span>
          <b style={{ color: 'var(--acc)' }}>●━</b> {t('Mean reward of the generation')}
        </span>
        <span>
          <b style={{ color: 'var(--chart-secondary)' }}>■╌</b> {t('Best reward of the generation')}
        </span>
        <span>{t('Generations without a reward are not drawn.')}</span>
      </div>
    </>
  );
}
