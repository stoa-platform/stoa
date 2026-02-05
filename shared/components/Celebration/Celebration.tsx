import { useState, useEffect, useCallback, createContext, useContext } from 'react';

// ============================================================================
// Types
// ============================================================================

export interface CelebrationOptions {
  /** Duration of the celebration in ms */
  duration?: number;
  /** Number of confetti particles */
  particleCount?: number;
  /** Spread angle in degrees */
  spread?: number;
}

interface CelebrationContextValue {
  celebrate: (options?: CelebrationOptions) => void;
}

// ============================================================================
// Context
// ============================================================================

const CelebrationContext = createContext<CelebrationContextValue | null>(null);

export function useCelebration() {
  const context = useContext(CelebrationContext);
  if (!context) {
    throw new Error('useCelebration must be used within a CelebrationProvider');
  }
  return context;
}

// ============================================================================
// Confetti Particle
// ============================================================================

interface Particle {
  id: number;
  x: number;
  y: number;
  color: string;
  rotation: number;
  scale: number;
  velocityX: number;
  velocityY: number;
}

const COLORS = [
  '#14b8a6', // primary (teal)
  '#06b6d4', // accent (cyan)
  '#22c55e', // success (green)
  '#f59e0b', // warning (amber)
  '#8b5cf6', // purple
  '#ec4899', // pink
];

function createParticle(id: number, centerX: number, centerY: number, spread: number): Particle {
  const angle = (Math.random() - 0.5) * spread * (Math.PI / 180);
  const velocity = 8 + Math.random() * 8;

  return {
    id,
    x: centerX,
    y: centerY,
    color: COLORS[Math.floor(Math.random() * COLORS.length)],
    rotation: Math.random() * 360,
    scale: 0.5 + Math.random() * 0.5,
    velocityX: Math.sin(angle) * velocity,
    velocityY: -Math.cos(angle) * velocity - Math.random() * 4,
  };
}

// ============================================================================
// Confetti Canvas Component
// ============================================================================

interface ConfettiProps {
  active: boolean;
  particleCount: number;
  spread: number;
  duration: number;
  onComplete: () => void;
}

function Confetti({ active, particleCount, spread, duration, onComplete }: ConfettiProps) {
  const [particles, setParticles] = useState<Particle[]>([]);

  useEffect(() => {
    if (!active) {
      setParticles([]);
      return;
    }

    // Create particles from center of screen
    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;

    const newParticles = Array.from({ length: particleCount }, (_, i) =>
      createParticle(i, centerX, centerY, spread)
    );
    setParticles(newParticles);

    // Animation loop
    let animationFrame: number;
    let startTime = Date.now();

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = elapsed / duration;

      if (progress >= 1) {
        setParticles([]);
        onComplete();
        return;
      }

      setParticles(prev =>
        prev.map(p => ({
          ...p,
          x: p.x + p.velocityX,
          y: p.y + p.velocityY,
          velocityY: p.velocityY + 0.3, // gravity
          rotation: p.rotation + 5,
        }))
      );

      animationFrame = requestAnimationFrame(animate);
    };

    animationFrame = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animationFrame);
    };
  }, [active, particleCount, spread, duration, onComplete]);

  if (!active || particles.length === 0) return null;

  return (
    <div className="fixed inset-0 pointer-events-none z-[200] overflow-hidden">
      {particles.map(particle => (
        <div
          key={particle.id}
          className="absolute w-3 h-3 rounded-sm"
          style={{
            left: particle.x,
            top: particle.y,
            backgroundColor: particle.color,
            transform: `rotate(${particle.rotation}deg) scale(${particle.scale})`,
            opacity: 0.9,
          }}
        />
      ))}
    </div>
  );
}

// ============================================================================
// Provider
// ============================================================================

const DEFAULT_OPTIONS: Required<CelebrationOptions> = {
  duration: 2000,
  particleCount: 50,
  spread: 90,
};

export function CelebrationProvider({ children }: { children: React.ReactNode }) {
  const [isActive, setIsActive] = useState(false);
  const [options, setOptions] = useState<Required<CelebrationOptions>>(DEFAULT_OPTIONS);

  const celebrate = useCallback((opts?: CelebrationOptions) => {
    setOptions({
      ...DEFAULT_OPTIONS,
      ...opts,
    });
    setIsActive(true);
  }, []);

  const handleComplete = useCallback(() => {
    setIsActive(false);
  }, []);

  return (
    <CelebrationContext.Provider value={{ celebrate }}>
      {children}
      <Confetti
        active={isActive}
        particleCount={options.particleCount}
        spread={options.spread}
        duration={options.duration}
        onComplete={handleComplete}
      />
    </CelebrationContext.Provider>
  );
}

export default CelebrationProvider;
