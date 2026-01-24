/**
 * Skip to Main Content Link (CAB-327 Accessibility)
 *
 * Hidden link that becomes visible on focus, allowing keyboard users
 * to skip navigation and jump directly to main content.
 */

export function SkipLink() {
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:bg-primary-600 focus:text-white focus:px-4 focus:py-2 focus:rounded-lg focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2"
    >
      Skip to main content
    </a>
  );
}

export default SkipLink;
