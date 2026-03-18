"use client";

import { useEffect, useRef, useState } from "react";

import type { IntelPerson } from "@/lib/types";

export interface AgentEvent {
  time: string;
  agent: string;
  msg: string;
}

interface StatusBarProps {
  people: IntelPerson[];
  activePerson: IntelPerson | null;
  events?: AgentEvent[];
  backendOnline?: boolean;
  error?: string | null;
}

export function StatusBar({ people, activePerson, events, backendOnline, error }: StatusBarProps) {
  const [eventIdx, setEventIdx] = useState(0);
  const [tick, setTick] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const snakeRef = useRef<{ pts: { x: number; y: number }[]; vx: number; vy: number }>({
    pts: [], vx: 0.7, vy: 0.25,
  });

  useEffect(() => {
    const id = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const formatElapsed = (s: number) => {
    const h = Math.floor(s / 3600).toString().padStart(2, "0");
    const m = Math.floor((s % 3600) / 60).toString().padStart(2, "0");
    const sec = (s % 60).toString().padStart(2, "0");
    return `${h}:${m}:${sec}`;
  };

  const displayEvents = events && events.length > 0 ? events : null;

  // Rotate through events every 4s
  useEffect(() => {
    if (!displayEvents) return;
    const id = setInterval(() => {
      setTick(false);
      setTimeout(() => {
        setEventIdx(i => (i + 1) % displayEvents.length);
        setTick(true);
      }, 200);
    }, 4000);
    return () => clearInterval(id);
  }, [displayEvents]);

  // Reset index when events change length
  useEffect(() => {
    setEventIdx(0);
    setTick(true);
  }, [displayEvents?.length]);

  // Snake canvas animation (idle state)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const parent = canvas.parentElement;
    if (parent) {
      canvas.width = parent.offsetWidth;
      canvas.height = parent.offsetHeight;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const snake = snakeRef.current;
    if (snake.pts.length === 0) {
      snake.pts = [{ x: W * 0.3, y: H / 2 }];
    }

    let raf: number;
    const animate = () => {
      const head = snake.pts[0];
      let nx = head.x + snake.vx;
      let ny = head.y + snake.vy;
      if (nx <= 0 || nx >= W) { snake.vx *= -1; nx = Math.max(0, Math.min(W, nx)); }
      if (ny <= 0 || ny >= H) { snake.vy *= -1; ny = Math.max(0, Math.min(H, ny)); }
      snake.pts.unshift({ x: nx, y: ny });
      if (snake.pts.length > 90) snake.pts.pop();

      ctx.clearRect(0, 0, W, H);
      for (let i = 1; i < snake.pts.length; i++) {
        const alpha = (1 - i / snake.pts.length) * 0.45;
        ctx.beginPath();
        ctx.moveTo(snake.pts[i - 1].x, snake.pts[i - 1].y);
        ctx.lineTo(snake.pts[i].x, snake.pts[i].y);
        ctx.strokeStyle = `rgba(120,180,80,${alpha.toFixed(3)})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      raf = requestAnimationFrame(animate);
    };

    if (!activePerson) {
      animate();
    } else {
      ctx.clearRect(0, 0, W, H);
      snakeRef.current.pts = [];
    }

    return () => cancelAnimationFrame(raf);
  }, [activePerson]);

  const evt = displayEvents ? displayEvents[eventIdx % displayEvents.length] : null;

  return (
    <div
      className="flex items-center justify-between px-4 border-t z-50 relative"
      style={{
        height: 32,
        background: "var(--bg-chrome)",
        borderColor: "rgba(120,180,80,.12)",
        fontFamily: "var(--font-mono)",
        color: "var(--text-dim)",
        fontSize: 10,
      }}
    >
      {/* LEFT — Active target or backend status */}
      {activePerson && (
        <div className="flex items-center shrink-0">
          {error ? (
            <span style={{ color: "rgba(239,68,68,.8)", letterSpacing: ".04em" }}>
              ERROR: <span style={{ fontWeight: 600 }}>{error.toUpperCase()}</span>
            </span>
          ) : backendOnline === false ? (
            <span style={{ color: "rgba(239,68,68,.7)", letterSpacing: ".04em" }}>
              BACKEND OFFLINE
            </span>
          ) : (
            <span style={{ color: "rgba(170,210,140,.7)" }}>
              ACTIVE:{" "}
              <span style={{ color: "rgba(170,210,140,.95)", letterSpacing: ".04em", fontWeight: 600 }}>
                {activePerson.name.toUpperCase()}
              </span>
            </span>
          )}
        </div>
      )}

      {/* CENTER — Snake (idle) or event ticker (active) */}
      <div style={{
        flex: 1, overflow: "hidden", position: "relative",
        padding: "0 24px", height: "100%", display: "flex", alignItems: "center",
      }}>
        {activePerson && evt ? (
          <div style={{
            width: "100%", textAlign: "center",
            opacity: tick ? 1 : 0, transition: "opacity .2s ease",
            letterSpacing: ".04em",
            whiteSpace: "nowrap", textOverflow: "ellipsis", overflow: "hidden",
          }}>
            <span style={{ color: "rgba(170,210,140,.4)" }}>[{evt.time}]</span>
            {" "}
            <span style={{ color: "rgba(170,210,140,.75)" }}>{evt.agent}:</span>
            {" "}
            <span style={{ color: "rgba(170,210,140,.6)" }}>{evt.msg}</span>
          </div>
        ) : activePerson && !evt ? (
          <div style={{
            width: "100%", textAlign: "center",
            letterSpacing: ".06em",
            color: "rgba(170,210,140,.35)",
          }}>
            Awaiting agent results...
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            style={{ width: "100%", height: "100%", display: "block" }}
          />
        )}
      </div>

      {/* RIGHT — Session timer (active target only) */}
      {activePerson && (
        <div style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
          <span style={{ color: "rgba(170,210,140,.7)" }}>SESSION: <span style={{ color: "rgba(170,210,140,.95)", fontWeight: 600 }}>{formatElapsed(elapsed)}</span></span>
        </div>
      )}
    </div>
  );
}
