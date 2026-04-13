'use client';

/**
 * Sparkline - minimal SVG line chart for dashboard cards.
 * No external chart library dependency.
 */

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  fillOpacity?: number;
  strokeWidth?: number;
}

export default function Sparkline({
  data,
  width = 120,
  height = 32,
  color = 'var(--accent)',
  fillOpacity = 0.1,
  strokeWidth = 1.5,
}: SparklineProps) {
  if (!data || data.length < 2) return null;

  const filtered = data.filter((v) => v !== null && v !== undefined && !isNaN(v));
  if (filtered.length < 2) return null;

  const min = Math.min(...filtered);
  const max = Math.max(...filtered);
  const range = max - min || 1;

  const padY = 2;
  const innerH = height - padY * 2;
  const stepX = width / (filtered.length - 1);

  const points = filtered.map((v, i) => {
    const x = i * stepX;
    const y = padY + innerH - ((v - min) / range) * innerH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const polyline = points.join(' ');

  // Fill polygon: close path along bottom
  const fillPath = `${points.join(' ')} ${width.toFixed(1)},${height} 0,${height}`;

  // Determine if trend is up or down for default color
  const isUp = filtered[filtered.length - 1] >= filtered[0];
  const resolvedColor = color === 'auto' ? (isUp ? 'var(--green)' : 'var(--red)') : color;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block' }}>
      <polygon points={fillPath} fill={resolvedColor} opacity={fillOpacity} />
      <polyline
        points={polyline}
        fill="none"
        stroke={resolvedColor}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Dot on latest point */}
      <circle
        cx={((filtered.length - 1) * stepX).toFixed(1)}
        cy={(padY + innerH - ((filtered[filtered.length - 1] - min) / range) * innerH).toFixed(1)}
        r="2"
        fill={resolvedColor}
      />
    </svg>
  );
}
