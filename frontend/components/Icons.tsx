const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;

export function TrashIcon() {
  return (
    <svg {...base}>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
    </svg>
  );
}

export function LogoIcon() {
  return (
    <svg {...base} width={20} height={20}>
      <path d="M3 11.5 21 4l-7.5 17-2.5-7z" />
    </svg>
  );
}
