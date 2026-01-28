// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * UACBadge Component
 *
 * Clickable badge indicating a contract uses UAC (Universal API Contract).
 * Shows a tooltip with all enabled bindings when clicked.
 *
 * Variants:
 * - default: "🔗 UAC ▼"
 * - compact: Just the link icon
 * - with-count: "🔗 UAC • 3 bindings ▼"
 *
 * Reference: CAB-564 - UAC Badge & Tooltips
 */

import React, { useState, useRef, useEffect } from 'react';
import { ProtocolBinding } from '../../types';
import { UACTooltip } from './UACTooltip';
import { Link2, ChevronDown } from 'lucide-react';

type BadgeVariant = 'default' | 'compact' | 'with-count';

interface UACBadgeProps {
  contractName: string;
  bindings: ProtocolBinding[];
  variant?: BadgeVariant;
  docsUrl?: string;
  className?: string;
}

export const UACBadge: React.FC<UACBadgeProps> = ({
  contractName,
  bindings,
  variant = 'default',
  docsUrl,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const enabledCount = bindings.filter((b) => b.enabled).length;

  // Close tooltip when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        tooltipRef.current &&
        !tooltipRef.current.contains(event.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Close on Escape key
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  const getBadgeContent = () => {
    switch (variant) {
      case 'compact':
        return <Link2 className="h-3.5 w-3.5" />;
      case 'with-count':
        return (
          <>
            <Link2 className="h-3.5 w-3.5" />
            <span>UAC</span>
            <span className="text-blue-400">•</span>
            <span>{enabledCount} bindings</span>
          </>
        );
      default:
        return (
          <>
            <Link2 className="h-3.5 w-3.5" />
            <span>UAC</span>
          </>
        );
    }
  };

  return (
    <div className={`relative inline-block ${className}`}>
      {/* Badge trigger */}
      <button
        ref={triggerRef}
        onClick={() => setIsOpen(!isOpen)}
        className={`
          inline-flex items-center gap-1.5
          px-2.5 py-1
          text-xs font-medium
          bg-blue-50 text-blue-700
          border border-blue-200
          rounded-full
          hover:bg-blue-100
          focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1
          transition-colors
          ${isOpen ? 'bg-blue-100' : ''}
        `}
        aria-expanded={isOpen}
        aria-haspopup="true"
        title="Universal API Contract - Click to learn more"
      >
        {getBadgeContent()}
        {variant !== 'compact' && (
          <ChevronDown
            className={`h-3 w-3 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          />
        )}
      </button>

      {/* Tooltip popover */}
      {isOpen && (
        <div
          ref={tooltipRef}
          className="
            absolute z-50
            mt-2
            bg-white
            rounded-lg
            shadow-lg
            border border-gray-200
            animate-in fade-in-0 zoom-in-95 duration-200
          "
          style={{
            left: '50%',
            transform: 'translateX(-50%)',
          }}
        >
          {/* Arrow */}
          <div
            className="
              absolute -top-2 left-1/2 -translate-x-1/2
              w-4 h-4
              bg-white
              border-l border-t border-gray-200
              rotate-45
            "
          />

          {/* Content */}
          <div className="relative p-4">
            <UACTooltip
              contractName={contractName}
              bindings={bindings}
              docsUrl={docsUrl}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default UACBadge;
