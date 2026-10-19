import { useProduct } from "@heteroes/product-ui";
import { compareColor } from "../../lib/chartColors";
import type { Series } from "../../lib/compare";

const W = 640, H = 300, LEFT = 52, RIGHT = 16, TOP = 14, BOTTOM = 36;

/** Mean reward per generation for several runs on one set of axes; the best reward is the dashed line of the same colour. */
export function CompareChart({ series, maxGeneration, maxReward, svgRef }: { series: Series[]; maxGeneration: number; maxReward: number; svgRef?: React.Ref<SVGSVGElement> }) {
  const { t } = useProduct();
  const top = Math.max(0.6, Math.ceil(maxReward * 10) / 10);
  const x = (generation: number) => LEFT + (maxGeneration === 0 ? (W - LEFT - RIGHT) / 2 : (generation / maxGeneration) * (W - LEFT - RIGHT));
  const y = (value: number) => TOP + (1 - value / top) * (H - TOP - BOTTOM);
  const path = (points: { generation: number; value: number }[]) => points.map((p, i) => `${i ? "L" : "M"}${x(p.generation).toFixed(1)} ${y(p.value).toFixed(1)}`).join(" ");
  return (
    <svg ref={svgRef} className="compare-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("Mean reward per generation for each selected run")} style={{ display: "block", width: "100%", height: "auto" }}>
      {[0, 1, 2, 3].map(step => { const value = (top * step) / 3; return <g key={step}><line x1={LEFT} x2={W - RIGHT} y1={y(value)} y2={y(value)} stroke="var(--line2)" /><text x={LEFT - 8} y={y(value) + 4} textAnchor="end" fontSize="11" fill="var(--mut)">{value.toFixed(2)}</text></g>; })}
      {Array.from({ length: maxGeneration + 1 }, (_, g) => <text key={g} x={x(g)} y={H - 14} textAnchor="middle" fontSize="11" fill="var(--mut)">{g + 1}</text>)}
      <text x={(LEFT + W - RIGHT) / 2} y={H - 1} textAnchor="middle" fontSize="11" fill="var(--mut)">{t("Generation")}</text>
      {series.map((item, index) => {
        const color = compareColor(index);
        return (
          <g key={item.id}>
            <path d={path(item.points.map(p => ({ generation: p.generation, value: p.best })))} fill="none" stroke={color} strokeWidth="1.5" strokeDasharray="5 4" opacity=".7" />
            <path d={path(item.points.map(p => ({ generation: p.generation, value: p.mean })))} fill="none" stroke={color} strokeWidth="2.5" />
            {item.points.map(p => <circle key={p.generation} cx={x(p.generation)} cy={y(p.mean)} r="3.5" fill={color}><title>{`${item.name} · ${t("Generation")} ${p.generation + 1}: ${p.mean.toFixed(4)}`}</title></circle>)}
          </g>
        );
      })}
    </svg>
  );
}
