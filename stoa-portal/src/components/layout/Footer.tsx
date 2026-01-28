// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { config } from '../../config';

export function Footer() {
  return (
    <footer className="bg-white border-t border-gray-200 py-4 px-6">
      <div className="flex flex-col sm:flex-row justify-between items-center gap-2 text-sm text-gray-500">
        <div>
          &copy; {new Date().getFullYear()} STOA Platform. All rights reserved.
        </div>
        <div className="flex items-center gap-4">
          <a
            href={config.services.docs.url}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-gray-700"
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
