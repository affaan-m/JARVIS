"use client";

import { motion } from "framer-motion";

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

  const pathD = `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`;

  return (
    <g className="string-glow">
      {/* Glow layer underneath */}
      <motion.path
        d={pathD}
        fill="none"
        stroke="var(--string-red)"
        strokeWidth="6"
        opacity="0"
        initial={{ opacity: 0 }}
        animate={{
          opacity: [0, 0.15, 0.05, 0.15, 0],
        }}
        transition={{
          duration: 3,
          repeat: Infinity,
          ease: "easeInOut",
          delay: 1.5,
        }}
        style={{ filter: "blur(4px)" }}
      />

      {/* Main string — draw-on effect */}
      <motion.path
        d={pathD}
        fill="none"
        stroke="var(--string-red)"
        strokeDasharray="8 4"
        strokeWidth="2"
        opacity="0.9"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 0.9 }}
        transition={{ duration: 1.5, ease: "easeOut" }}
      />

      {/* Label fades in after line draws */}
      <motion.text
        x={midpointX}
        y={midpointY}
        textAnchor="middle"
        fill="var(--text-ui)"
        fontFamily="var(--font-mono)"
        fontSize="10"
        letterSpacing="1.5"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.2, duration: 0.4 }}
      >
        {label.toUpperCase()}
      </motion.text>
    </g>
  );
}
