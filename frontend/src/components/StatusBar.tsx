"use client";

import { useEffect, useRef, useState } from "react";

import type { IntelPerson } from "@/lib/types";

interface StatusBarProps {
  people: IntelPerson[];
  activePerson: IntelPerson | null;
}

// Demo agent events shown in the center ticker
const DEMO_EVENTS = [
  { time: "21:04:26", agent: "github-agent", msg: "CI scaffolding complete — 3 workflows active" },
  { time: "21:03:12", agent: "linkedin-agent", msg: "Profile enrichment pass complete" },
  { time: "21:02:44", agent: "exa-agent", msg: "Fast lookup finished — 7 signals found" },
  { time: "21:02:08", agent: "browser-use", msg: "Twitter handle resolved via reverse lookup" },
  { time: "21:01:33", agent: "orchestrator", msg: "Spawning tier-2 agents for active subject" },
  { time: "21:00:55", agent: "face-id", msg: "ArcFace embedding matched — confidence 0.94" },
  { time: "21:00:22", agent: "capture", msg: "Frame extracted from Meta glasses stream" },
];

export function StatusBar({ people, activePerson }: StatusBarProps) {
  const [eventIdx, setEventIdx] = useState(0);
  const [tick, setTick] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const snakeRef = useRef<{ pts: { x: number; y: number }[]; vx: number; vy: number }>({
    pts: [], vx: 1.8, vy: 0.6,
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

  const totalSources = people.reduce((acc, p) => acc + p.sources.length, 0);

  const counts = {
    scanning: people.filter(p => p.status === "scanning").length,
    complete: people.filter(p => p.status === "complete").length,
    inactive: people.filter(p => p.status === "inactive").length,
  };

  // Rotate through events every 4s
  useEffect(() => {
    const id = setInterval(() => {
      setTick(false);
      setTimeout(() => {
        setEventIdx(i => (i + 1) % DEMO_EVENTS.length);
        setTick(true);
      }, 200);
    }, 4000);
    return () => clearInterval(id);
  }, []);

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
      if (nx <= 2 || nx >= W - 2) { snake.vx *= -1; nx = Math.max(2, Math.min(W - 2, nx)); }
      if (ny <= 2 || ny >= H - 2) { snake.vy *= -1; ny = Math.max(2, Math.min(H - 2, ny)); }
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

  const evt = DEMO_EVENTS[eventIdx];

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
      {/* LEFT — Status counts (active target only) */}
      {activePerson && (
        <div className="flex items-center gap-5 shrink-0">
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--status-pending)", flexShrink: 0 }} />
            PENDING:{" "}
            <span style={{ color: "var(--text-ui)" }}>{counts.inactive}</span>
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{
              display: "inline-block", width: 6, height: 6, borderRadius: "50%",
              background: "var(--status-researching)", flexShrink: 0,
              animation: counts.scanning > 0 ? "scanPulse 2s ease-in-out infinite" : "none",
            }} />
            RESEARCHING:{" "}
            <span style={{ color: "var(--text-ui)" }}>{counts.scanning}</span>
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--status-complete)", flexShrink: 0 }} />
            COMPLETE:{" "}
            <span style={{ color: "var(--text-ui)" }}>{counts.complete}</span>
          </span>

          <span style={{ color: "rgba(120,180,80,.2)" }}>│</span>
          <span style={{ color: "rgba(120,180,80,.5)" }}>
            ACTIVE:{" "}
            <span style={{ color: "var(--intel-green)", letterSpacing: ".04em" }}>
              {activePerson.name.toUpperCase()}
            </span>
          </span>
        </div>
      )}

      {/* CENTER — Snake (idle) or event ticker (active) */}
      <div style={{
        flex: 1, overflow: "hidden", position: "relative",
        padding: "0 24px", height: "100%", display: "flex", alignItems: "center",
      }}>
        {activePerson ? (
          <div style={{
            width: "100%", textAlign: "center",
            opacity: tick ? 1 : 0, transition: "opacity .2s ease",
            color: "rgba(120,180,80,.45)", letterSpacing: ".04em",
            whiteSpace: "nowrap", textOverflow: "ellipsis", overflow: "hidden",
          }}>
            <span style={{ color: "rgba(120,180,80,.25)" }}>[{evt.time}]</span>
            {" "}
            <span style={{ color: "rgba(120,180,80,.55)" }}>{evt.agent}:</span>
            {" "}
            {evt.msg}
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            style={{ width: "100%", height: "100%", display: "block" }}
          />
        )}
      </div>

      {/* RIGHT — Totals + analytics (active target only) */}
      {activePerson && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <span>SOURCES: <span style={{ color: "var(--text-ui)" }}>{totalSources}</span></span>
          <span style={{ color: "rgba(120,180,80,.2)" }}>│</span>
          <span>SESSION: <span style={{ color: "var(--text-ui)" }}>{formatElapsed(elapsed)}</span></span>
          <span style={{ color: "rgba(120,180,80,.2)" }}>│</span>
          <span>TARGETS ACQUIRED: <span style={{ color: "var(--text-ui)" }}>{people.length}</span></span>
        </div>
      )}
    </div>
  );
}
