import type { ReactNode } from "react";

interface IconProps {
  size?: number;
  strokeWidth?: number;
  children: ReactNode;
}

function Icon({ size = 18, strokeWidth = 1.8, children }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function LogoMark() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="12" width="4" height="9" rx="1.5" fill="#0F766E" opacity=".4" />
      <rect x="10" y="7" width="4" height="14" rx="1.5" fill="#0F766E" opacity=".7" />
      <rect x="17" y="3" width="4" height="18" rx="1.5" fill="#0F766E" />
    </svg>
  );
}

export function DashboardIcon() {
  return (
    <Icon>
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </Icon>
  );
}

export function FlaskIcon() {
  return (
    <Icon>
      <path d="M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2.2h12.4a1.5 1.5 0 0 0 1.3-2.2L14 9V3" />
      <path d="M7.5 15h9" />
    </Icon>
  );
}

export function ChipIcon() {
  return (
    <Icon>
      <rect x="5" y="5" width="14" height="14" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
    </Icon>
  );
}

export function ListIcon() {
  return (
    <Icon>
      <path d="M4 6h16M4 12h10M4 18h13" />
    </Icon>
  );
}

export function FileIcon() {
  return (
    <Icon>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </Icon>
  );
}

export function RefreshIcon() {
  return (
    <Icon size={16} strokeWidth={2}>
      <path d="M21 12a9 9 0 1 1-3-6.7L21 8" />
      <path d="M21 3v5h-5" />
    </Icon>
  );
}

export function PlusIcon() {
  return (
    <Icon size={16} strokeWidth={2}>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  );
}

export function CopyIcon() {
  return (
    <Icon size={15} strokeWidth={2}>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V6a2 2 0 0 1 2-2h9" />
    </Icon>
  );
}
