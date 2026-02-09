interface StoaLoaderProps {
  /** Full screen overlay or inline content area */
  variant?: 'fullscreen' | 'inline';
  /** Override SVG size in px (default: 64 fullscreen, 48 inline) */
  size?: number;
}

export function StoaLoader({ variant = 'inline', size }: StoaLoaderProps) {
  const svgSize = size ?? (variant === 'fullscreen' ? 64 : 48);

  const wrapperClass =
    variant === 'fullscreen'
      ? 'min-h-screen bg-gray-50 dark:bg-neutral-900 flex items-center justify-center transition-colors'
      : 'flex items-center justify-center min-h-[400px]';

  return (
    <div className={wrapperClass}>
      <div className="text-center">
        <div className="stoa-loader-breathe mx-auto">
          <svg
            viewBox="-2 -2 36 36"
            width={svgSize}
            height={svgSize}
            className="stoa-loader-glow"
            role="img"
            aria-label="Loading"
          >
            {/* Spinning ring */}
            <circle
              cx="16"
              cy="16"
              r="17"
              fill="none"
              stroke="#059669"
              strokeWidth="1.2"
              strokeDasharray="27 80"
              strokeLinecap="round"
              className="stoa-loader-ring"
              opacity="0.5"
            />
            <defs>
              <linearGradient id="stoaLoaderGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#047857" />
                <stop offset="100%" stopColor="#059669" />
              </linearGradient>
            </defs>
            {/* Main circle */}
            <circle cx="16" cy="16" r="15" fill="url(#stoaLoaderGrad)" />
            {/* S path */}
            <path
              d="M10 11 Q10 8,16 8 Q22 8,22 11 Q22 14,16 14 Q10 14,10 17 Q10 20,16 20 Q22 20,22 24 Q22 27,16 27"
              stroke="white"
              strokeWidth="2.5"
              strokeLinecap="round"
              fill="none"
            />
            {/* Orbital dots */}
            <circle cx="8" cy="14" r="1.5" fill="white" className="stoa-loader-dot-1" />
            <circle cx="24" cy="14" r="1.5" fill="white" className="stoa-loader-dot-2" />
            <circle cx="8" cy="20" r="1.5" fill="white" className="stoa-loader-dot-3" />
            <circle cx="24" cy="20" r="1.5" fill="white" className="stoa-loader-dot-4" />
          </svg>
        </div>
      </div>
    </div>
  );
}
