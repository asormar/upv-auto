interface IconProps {
  size?: number;
}

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
});

export const Clock = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
);

export const SignOut = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
    <path d="M10 8l-4 4 4 4" />
    <path d="M6 12h9" />
  </svg>
);

export const Check = ({ size = 16 }: IconProps) => (
  <svg {...base(size)} strokeWidth={2}>
    <path d="M5 12.5l4.5 4.5L19 7" />
  </svg>
);

export const Plus = ({ size = 16 }: IconProps) => (
  <svg {...base(size)} strokeWidth={2}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const Minus = ({ size = 16 }: IconProps) => (
  <svg {...base(size)} strokeWidth={2}>
    <path d="M5 12h14" />
  </svg>
);

export const Refresh = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M20 12a8 8 0 1 1-2.6-5.9" />
    <path d="M20 4v5h-5" />
  </svg>
);

export const Sun = ({ size = 16 }: IconProps) => (
  <svg {...base(size)} strokeWidth={2}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
  </svg>
);

export const Moon = ({ size = 16 }: IconProps) => (
  <svg {...base(size)} strokeWidth={2}>
    <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
  </svg>
);

export const Shield = ({ size = 15 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

export const Alert = ({ size = 15 }: IconProps) => (
  <svg {...base(size)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v5M12 16h.01" />
  </svg>
);

export const Eye = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

export const EyeOff = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}>
    <path d="M3 3l18 18" />
    <path d="M9.9 4.24A10.4 10.4 0 0 1 12 4c6.4 0 10 7 10 7a17.6 17.6 0 0 1-3 3.9M6.6 6.6C4.1 8.3 2 12 2 12s3.6 7 10 7a10 10 0 0 0 4-.8" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
  </svg>
);
