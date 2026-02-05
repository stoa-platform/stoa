// ============================================================================
// STOA Motion Utilities
// Consistent animation tokens for Apple-like feel
// ============================================================================

/**
 * CSS transition timing functions (easing)
 */
export const easing = {
  /** Standard easing for most animations */
  default: 'cubic-bezier(0.4, 0, 0.2, 1)',
  /** Ease-out for elements entering the screen */
  easeOut: 'cubic-bezier(0, 0, 0.2, 1)',
  /** Ease-in for elements leaving the screen */
  easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
  /** Ease-in-out for elements moving on screen */
  easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
  /** Spring-like overshoot for playful animations */
  spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
  /** Smooth deceleration */
  smooth: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
} as const;

/**
 * Duration tokens (in milliseconds)
 */
export const duration = {
  /** Instant feedback (hover states, toggles) */
  instant: 75,
  /** Very fast (micro-interactions) */
  fast: 150,
  /** Normal transitions */
  normal: 200,
  /** Slightly slower for emphasis */
  slow: 300,
  /** Complex animations (modals, page transitions) */
  slower: 400,
  /** Very slow for dramatic effect */
  slowest: 500,
} as const;

/**
 * Pre-built CSS transition strings
 */
export const transition = {
  /** Fast opacity change */
  fade: `opacity ${duration.fast}ms ${easing.default}`,
  /** Standard all-property transition */
  default: `all ${duration.normal}ms ${easing.default}`,
  /** Transform-only transition */
  transform: `transform ${duration.normal}ms ${easing.default}`,
  /** Scale with spring effect */
  scale: `transform ${duration.slow}ms ${easing.spring}`,
  /** Slide animations */
  slide: `transform ${duration.normal}ms ${easing.easeOut}`,
  /** Color transitions */
  colors: `background-color ${duration.fast}ms ${easing.default}, border-color ${duration.fast}ms ${easing.default}, color ${duration.fast}ms ${easing.default}`,
  /** Shadow transitions */
  shadow: `box-shadow ${duration.normal}ms ${easing.default}`,
} as const;

/**
 * CSS animation keyframe names (must match tailwind.config.js)
 */
export const keyframes = {
  fadeIn: 'fade-in',
  fadeOut: 'fade-out',
  scaleIn: 'scale-in',
  scaleOut: 'scale-out',
  slideInUp: 'slide-in-up',
  slideInDown: 'slide-in-down',
  slideInLeft: 'slide-in-left',
  slideInRight: 'slide-in-right',
  pulse: 'pulse',
  spin: 'spin',
  bounce: 'bounce',
} as const;

/**
 * Tailwind animation class names
 */
export const animate = {
  fadeIn: 'animate-fade-in',
  scaleIn: 'animate-scale-in',
  slideIn: 'animate-slide-in',
  pulse: 'animate-pulse',
  spin: 'animate-spin',
  bounce: 'animate-bounce',
} as const;

/**
 * Helper to create staggered animation delays
 * @param index Item index in a list
 * @param baseDelay Base delay in ms
 * @param staggerDelay Delay between each item in ms
 */
export function staggerDelay(index: number, baseDelay = 0, staggerDelay = 50): string {
  return `${baseDelay + index * staggerDelay}ms`;
}

/**
 * Helper to create a style object with staggered animation delay
 */
export function staggerStyle(index: number, baseDelay = 0, staggerMs = 50): React.CSSProperties {
  return {
    animationDelay: staggerDelay(index, baseDelay, staggerMs),
  };
}

/**
 * Reduced motion preference check
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Get animation class with reduced motion support
 */
export function getAnimationClass(animation: keyof typeof animate): string {
  if (prefersReducedMotion()) {
    return ''; // No animation for users who prefer reduced motion
  }
  return animate[animation];
}

export default {
  easing,
  duration,
  transition,
  keyframes,
  animate,
  staggerDelay,
  staggerStyle,
  prefersReducedMotion,
  getAnimationClass,
};
