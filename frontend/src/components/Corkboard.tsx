"use client";

import { useRef, useState, useCallback } from "react";

import type { ConnectionRecord, PersonRecord } from "@/lib/types";

import { ConnectionLine } from "./ConnectionLine";
import { PersonCard } from "./PersonCard";

interface CorkboardProps {
  persons: PersonRecord[];
  connections: ConnectionRecord[];
  onPersonClick: (id: string) => void;
  selectedPersonId: string | null;
}

export function Corkboard({ persons, connections, onPersonClick, selectedPersonId }: CorkboardProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const lastMouse = useRef({ x: 0, y: 0 });

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    // Only pan if clicking the board itself (not a card)
    if ((e.target as HTMLElement).closest("[data-person-card]")) return;
    setIsPanning(true);
    lastMouse.current = { x: e.clientX, y: e.clientY };
  }, []);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isPanning) return;
      const dx = e.clientX - lastMouse.current.x;
      const dy = e.clientY - lastMouse.current.y;
      lastMouse.current = { x: e.clientX, y: e.clientY };
      setPan((prev) => ({ x: prev.x + dx, y: prev.y + dy }));
    },
    [isPanning]
  );

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((prev) => Math.max(0.3, Math.min(3, prev - e.deltaY * 0.001)));
  }, []);

  // Build person position lookup
  const personPositions = new Map(persons.map((p) => [p._id, p.boardPosition]));

  return (
    <div
      ref={containerRef}
      className="w-full h-full cursor-grab active:cursor-grabbing overflow-hidden"
      style={{ background: "var(--board-bg)" }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
    >
      {/* Board surface with subtle grid */}
      <div
        className="relative w-full h-full"
        style={{
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
          transformOrigin: "center center",
          backgroundImage: `
            linear-gradient(rgba(120,180,80,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(120,180,80,0.03) 1px, transparent 1px)
          `,
          backgroundSize: "40px 40px",
        }}
      >
        {/* SVG layer for connection lines */}
        <svg
          className="absolute inset-0 w-full h-full pointer-events-none"
          style={{ overflow: "visible" }}
        >
          {connections.map((conn) => {
            const posA = personPositions.get(conn.personAId);
            const posB = personPositions.get(conn.personBId);
            if (!posA || !posB) return null;
            return (
              <ConnectionLine
                key={conn._id}
                from={posA}
                to={posB}
                label={conn.relationshipType}
              />
            );
          })}
        </svg>

        {/* Person cards */}
        {persons.map((person, index) => (
          <PersonCard
            key={person._id}
            person={person}
            isSelected={selectedPersonId === person._id}
            onClick={() => onPersonClick(person._id)}
            index={index}
          />
        ))}
      </div>
    </div>
  );
}
