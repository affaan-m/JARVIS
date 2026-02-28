"use client";

interface ConnectionLineProps {
  from: { x: number; y: number };
  to: { x: number; y: number };
  label: string;
}

export function ConnectionLine({ from, to, label }: ConnectionLineProps) {
  const startX = from.x + 110;
  const startY = from.y + 120;
  const endX = to.x + 110;
  const endY = to.y + 120;
  const controlX = (startX + endX) / 2;
  const controlY = Math.min(startY, endY) - 80;
  const midpointX = (startX + endX) / 2;
  const midpointY = (startY + endY) / 2 - 36;

  return (
    <g className="string-glow">
      <path
        d={`M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`}
        fill="none"
        stroke="var(--string-red)"
        strokeDasharray="8 4"
        strokeWidth="2"
        opacity="0.9"
      />
      <text
        x={midpointX}
        y={midpointY}
        textAnchor="middle"
        fill="var(--text-ui)"
        fontFamily="var(--font-mono)"
        fontSize="10"
        letterSpacing="1.5"
      >
        {label.toUpperCase()}
      </text>
    </g>
  );
}
