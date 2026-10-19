import type { ReactNode } from 'react';

interface StatProps {
  label: string;
  value: ReactNode;
  unit?: ReactNode;
  note: string;
}

export function Stat({ label, value, unit, note }: StatProps) {
  return (
    <div className="stat">
      <span className="l">{label}</span>
      <span className="v">
        {value} {unit && <small>{unit}</small>}
      </span>
      <span className="n">{note}</span>
    </div>
  );
}
