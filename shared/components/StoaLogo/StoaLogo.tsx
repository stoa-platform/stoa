interface StoaLogoProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizes = { sm: 24, md: 32, lg: 48 };

export function StoaLogo({ size = 'md', className }: StoaLogoProps) {
  const px = sizes[size];
  return (
    <svg
      viewBox="0 0 32 32"
      width={px}
      height={px}
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="stoaLogoGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#047857" />
          <stop offset="100%" stopColor="#059669" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="15" fill="url(#stoaLogoGrad)" />
      <path
        d="M10 11 Q10 8,16 8 Q22 8,22 11 Q22 14,16 14 Q10 14,10 17 Q10 20,16 20 Q22 20,22 24 Q22 27,16 27"
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="8" cy="14" r="1.5" fill="white" opacity="0.8" />
      <circle cx="24" cy="14" r="1.5" fill="white" opacity="0.8" />
      <circle cx="8" cy="20" r="1.5" fill="white" opacity="0.8" />
      <circle cx="24" cy="20" r="1.5" fill="white" opacity="0.8" />
    </svg>
  );
}
