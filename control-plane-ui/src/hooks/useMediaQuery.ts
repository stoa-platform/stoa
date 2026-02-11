import { useState, useEffect } from 'react';

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches
  );

  useEffect(() => {
    const media = window.matchMedia(query);
    const handler = () => setMatches(media.matches);
    media.addEventListener('change', handler);
    return () => media.removeEventListener('change', handler);
  }, [query]);

  return matches;
}
