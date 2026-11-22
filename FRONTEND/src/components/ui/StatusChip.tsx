import React from 'react';
import clsx from 'clsx';

export type StatusType =
  | 'APPROVED'
  | 'ROUTINE'
  | 'PRIORITY'
  | 'URGENT'
  | 'PENDING'
  | 'NEEDS_INFO'
  | 'REJECTED'
  | 'SUSPENDED'
  | 'LOCKED'
  | 'INFO';

interface StatusChipProps {
  status: StatusType | string;
  label?: string;
  size?: 'sm' | 'md';
  className?: string;
}

/**
 * Status chips: full pills (rounded-full).
 * Rule: Red is NEVER used for status chips except urgent clinical triage flags.
 * Amber #B7791F = priority, Teal #1F7A5C = routine/approved, Slate #6B7280 = info
 */
export const StatusChip: React.FC<StatusChipProps> = ({
  status,
  label,
  size = 'md',
  className = '',
}) => {
  const norm = (status || '').toUpperCase();

  const getStyle = () => {
    switch (norm) {
      case 'APPROVED':
      case 'ROUTINE':
        return 'bg-emerald-50 text-[#1F7A5C] border border-emerald-200/60';
      case 'PRIORITY':
      case 'NEEDS_INFO':
        return 'bg-amber-50 text-[#B7791F] border border-amber-200/60';
      case 'URGENT':
        return 'bg-blush text-cardinal border border-red-200';
      case 'PENDING':
        return 'bg-blue-50 text-blue-700 border border-blue-200/60';
      case 'REJECTED':
      case 'SUSPENDED':
      case 'LOCKED':
        return 'bg-stone-100 text-stone-700 border border-stone-300';
      default:
        return 'bg-gray-100 text-[#6B7280] border border-gray-200';
    }
  };

  const getDotColor = () => {
    switch (norm) {
      case 'APPROVED':
      case 'ROUTINE':
        return 'bg-[#1F7A5C]';
      case 'PRIORITY':
      case 'NEEDS_INFO':
        return 'bg-[#B7791F]';
      case 'URGENT':
        return 'bg-cardinal';
      case 'PENDING':
        return 'bg-blue-600';
      default:
        return 'bg-[#6B7280]';
    }
  };

  const displayText =
    label ||
    norm.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 font-medium rounded-full select-none tabular-nums',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs',
        getStyle(),
        className
      )}
    >
      <span className={clsx('w-1.5 h-1.5 rounded-full', getDotColor())} />
      <span>{displayText}</span>
    </span>
  );
};
