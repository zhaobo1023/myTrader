'use client';

/**
 * MiniSparkline - simple SVG polyline sparkline for time series data.
 */

interface SparkPoint {
  date?: string;
  value?: number | null;
  [key: string]: unknown;
}

interface MiniSparklineProps {
  data: SparkPoint[];
  valueKey?: string;
  width?: number;
  height?: number;
  color?: string;
  className?: string;
}

export default function MiniSparkline({
  data,
  valueKey = 'value',
  width = 120,
  height = 40,
  color = '#3b82f6',
  className = '',
}: MiniSparklineProps) {
  const values = data
    .map((d) => {
      const v = d[valueKey];
      return typeof v === 'number' ? v : null;
    })
    .filter((v): v is number => v !== null);

  if (values.length < 2) {
    return <div className={`w-[${width}px] h-[${height}px] ${className}`} />;
  }

  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const rangeV = maxV - minV || 1;
  const pad = 4;

  const points = values
    .map((v, i) => {
      const x = pad + (i / (values.length - 1)) * (width - pad * 2);
      const y = pad + (1 - (v - minV) / rangeV) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const lastIdx = values.length - 1;
  const lastX = pad + (width - pad * 2);
  const lastY = pad + (1 - (values[lastIdx] - minV) / rangeV) * (height - pad * 2);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastX} cy={lastY} r="2.5" fill={color} />
    </svg>
  );
}
