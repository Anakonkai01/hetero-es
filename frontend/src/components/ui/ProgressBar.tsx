import { percent } from "../../lib/format";

interface ProgressBarProps {
  done: number;
  total: number;
  large?: boolean;
}

export function ProgressBar({ done, total, large }: ProgressBarProps) {
  return (
    <div
      className="bar"
      style={large ? { height: 8, borderRadius: 4 } : undefined}
    >
      <div className="fill" style={{ width: `${percent(done, total)}%` }} />
    </div>
  );
}
