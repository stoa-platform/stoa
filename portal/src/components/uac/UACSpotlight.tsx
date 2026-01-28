// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * UACSpotlight Component
 *
 * First-time user educational banner explaining Universal API Contract (UAC).
 * Shows at the bottom of the screen with a "Did you know?" message.
 * Can be dismissed and persists dismissal in localStorage via useUACSpotlight hook.
 *
 * Reference: CAB-564 - UAC Badge & Tooltips
 */

import React from 'react';
import { X, Lightbulb, ExternalLink } from 'lucide-react';

interface UACSpotlightProps {
  /** Called when user dismisses the spotlight */
  onDismiss: () => void;
  /** URL to UAC documentation */
  docsUrl?: string;
  /** Custom class for positioning */
  className?: string;
}

export const UACSpotlight: React.FC<UACSpotlightProps> = ({
  onDismiss,
  docsUrl = '/docs/uac',
  className = '',
}) => {
  return (
    <div
      className={`
        fixed bottom-4 left-1/2 -translate-x-1/2
        w-full max-w-xl
        bg-white
        border border-blue-200
        rounded-lg
        shadow-lg
        animate-in slide-in-from-bottom-4 fade-in-0 duration-300
        z-50
        ${className}
      `}
      role="alert"
      aria-live="polite"
    >
      {/* Blue accent bar at top */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-400 to-blue-600 rounded-t-lg" />

      <div className="p-4 pt-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2 text-blue-600">
            <Lightbulb className="h-5 w-5 flex-shrink-0" />
            <span className="font-semibold text-sm">Did you know?</span>
          </div>

          {/* Close button */}
          <button
            onClick={onDismiss}
            className="
              p-1 -m-1
              text-gray-400 hover:text-gray-600
              rounded-md
              hover:bg-gray-100
              transition-colors
              focus:outline-none focus:ring-2 focus:ring-blue-500
            "
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="mt-2 ml-7">
          <p className="text-gray-800 font-medium">
            STOA uses Universal API Contracts (UAC).
          </p>
          <p className="text-gray-600 text-sm mt-1">
            Define your API once, expose it everywhere — REST, MCP, GraphQL, and
            more from a single definition.
          </p>
        </div>

        {/* Action buttons */}
        <div className="mt-4 ml-7 flex items-center gap-3">
          <a
            href={docsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="
              inline-flex items-center gap-1.5
              px-3 py-1.5
              text-sm font-medium
              text-blue-600
              border border-blue-200
              rounded-md
              hover:bg-blue-50
              transition-colors
              focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1
            "
          >
            See how it works
            <ExternalLink className="h-3.5 w-3.5" />
          </a>

          <button
            onClick={onDismiss}
            className="
              px-3 py-1.5
              text-sm font-medium
              text-gray-700
              bg-gray-100
              rounded-md
              hover:bg-gray-200
              transition-colors
              focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-1
            "
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
};

export default UACSpotlight;
