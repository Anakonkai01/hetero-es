import {useProduct} from '@heteroes/product-ui';
import type { BadgeInfo, Tone } from "../../lib/labels";

interface BadgeProps {
  info?: BadgeInfo;
  tone?: Tone;
  label?: string;
  title?: string;
}

export function Badge({ info, tone, label, title }: BadgeProps) {
  const {t}=useProduct();
  const resolvedTone = info?.tone ?? tone ?? "neutral";

  return (
    <span
      className={`badge ${resolvedTone}`}
      title={title ?? (info?.title?t(info.title):undefined)}
    >
      {label ?? (info?.label?t(info.label):undefined)}
    </span>
  );
}
