import { config } from '../../config';

export function Footer() {
  return (
    <footer className="bg-white dark:bg-neutral-900 border-t border-neutral-200 dark:border-neutral-800 py-4 px-6 transition-colors">
      <div className="flex flex-col sm:flex-row justify-between items-center gap-2 text-sm text-neutral-500 dark:text-neutral-400">
        <div>&copy; {new Date().getFullYear()} STOA Platform. All rights reserved.</div>
        <div className="flex items-center gap-4">
          <a
            href={config.services.docs.url}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
          >
            Documentation
          </a>
          <span>|</span>
          <span>v{config.app.version}</span>
        </div>
      </div>
    </footer>
  );
}
