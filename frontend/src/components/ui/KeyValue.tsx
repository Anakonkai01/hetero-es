import type { ReactNode } from "react";

interface KeyValueProps {
  label: string;
  children: ReactNode;
  mono?: boolean;
}

export function KeyValue({ label, children, mono }: KeyValueProps) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={mono ? "mono" : undefined}>{children}</dd>
    </div>
  );
}
