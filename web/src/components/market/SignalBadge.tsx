'use client';

/**
 * SignalBadge - colored badge for signal labels.
 * No emoji. Color coded by signal type.
 */

const SIGNAL_COLORS: Record<string, string> = {
  // Bullish / cheap / good
  undervalued: 'bg-green-100 text-green-800',
  attractive: 'bg-green-100 text-green-800',
  very_attractive: 'bg-green-100 text-green-800',
  low: 'bg-green-100 text-green-800',
  bottom: 'bg-green-100 text-green-800',
  buy_opportunity: 'bg-green-100 text-green-800',
  inflow: 'bg-green-100 text-green-800',
  expansion: 'bg-green-100 text-green-800',
  hk_preferred: 'bg-green-100 text-green-800',
  complacent: 'bg-blue-100 text-blue-800',
  // Neutral
  neutral: 'bg-gray-100 text-gray-700',
  normal: 'bg-gray-100 text-gray-700',
  fair: 'bg-gray-100 text-gray-700',
  moderate: 'bg-yellow-100 text-yellow-800',
  weak: 'bg-yellow-100 text-yellow-800',
  // Bearish / expensive / bad
  overvalued: 'bg-red-100 text-red-800',
  expensive: 'bg-red-100 text-red-800',
  bubble: 'bg-red-100 text-red-800',
  panic: 'bg-red-100 text-red-800',
  high: 'bg-red-100 text-red-800',
  overextended: 'bg-red-100 text-red-800',
  outflow: 'bg-red-100 text-red-800',
  contraction: 'bg-red-100 text-red-800',
  a_preferred: 'bg-red-100 text-red-800',
  fearful: 'bg-orange-100 text-orange-800',
  confirmed: 'bg-blue-100 text-blue-800',
};

const SIGNAL_LABELS: Record<string, string> = {
  undervalued: 'Undervalued',
  overvalued: 'Overvalued',
  neutral: 'Neutral',
  fair: 'Fair',
  attractive: 'Attractive',
  very_attractive: 'Very Attractive',
  expensive: 'Expensive',
  low: 'Low',
  normal: 'Normal',
  high: 'High',
  bottom: 'Bottom',
  bubble: 'Bubble',
  complacent: 'Complacent',
  fearful: 'Fearful',
  panic: 'Panic',
  inflow: 'Inflow',
  outflow: 'Outflow',
  expansion: 'Expansion',
  contraction: 'Contraction',
  buy_opportunity: 'Buy Signal',
  overextended: 'Overextended',
  hk_preferred: 'HK Preferred',
  a_preferred: 'A Preferred',
  moderate: 'Moderate',
  weak: 'Weak',
  confirmed: 'Confirmed',
};

interface SignalBadgeProps {
  signal: string;
  className?: string;
}

export default function SignalBadge({ signal, className = '' }: SignalBadgeProps) {
  const colorClass = SIGNAL_COLORS[signal] ?? 'bg-gray-100 text-gray-600';
  const label = SIGNAL_LABELS[signal] ?? signal;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colorClass} ${className}`}
    >
      {label}
    </span>
  );
}
