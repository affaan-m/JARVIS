"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { demoPeople } from "@/lib/demo-data";
import type { IntelPerson, IntelSource } from "@/lib/types";
import { CameraFeed } from "./CameraFeed";
import { Sidebar } from "./Sidebar";

/*
 * ============================================================
 * INTELLIGENCE CORKBOARD — v5
 * ============================================================
 *
 * DATA INTEGRATION NOTES (for real implementation):
 *
 * 1. PERSON LIST (left sidebar):
 *    - `people` state holds all scanned people
 *    - Each person: { id, name, status, sources[], summary }
 *    - status: "complete" | "scanning" | "inactive"
 *    - When Browser Use agent starts scanning a new person:
 *      a) Add them to `people` with status "scanning"
 *      b) The list animates them to the top (push-down effect)
 *      c) Set them as `activePerson` to show on board
 *    - When all sources are gathered, flip status to "complete"
 *
 * 2. SOURCES (board documents):
 *    - Each source: { id, nm, tp, sn, loading? }
 *    - nm = source name, tp = source type, sn = snippet text
 *    - When a new source is found by Browser Use:
 *      a) Add to the active person's sources array
 *      b) It will appear on the board with shimmer loading state
 *      c) When content is ready, set loading=false
 *
 * 3. SUMMARY DOCUMENT (blue center doc):
 *    - Generated/updated as sources come in
 *    - person.summary = { nm: "PERSON NAME", sm: "summary text" }
 *    - Appears on first source, updates as more arrive
 *
 * 4. CAMERA FEED:
 *    - `camConnected` state controls connected/disconnected UI
 *    - Set to true when Meta glasses stream is active
 *    - The <video> element or canvas can replace the placeholder
 *      inside CameraFeed component's screen div
 *
 * 5. BOARD TRANSITIONS:
 *    - When switching people, `boardFade` controls crossfade
 *    - Old person's docs fade out, new person's fade in
 *    - All position/rotation data is stored per-person
 *
 * 6. SEARCH BAR:
 *    - Currently filters the `people` list client-side
 *    - Can be extended to trigger Browser Use agent scans
 *      for names not in the list
 * ============================================================
 */

const BW = 860, BH = 680, GW = 168, GH = 108, BDW = 210, BDH = 150, FR = 14, SIDE_W = 270;
const ZM = [0.48, 1, 1.65];
const CAM_W = 240, CAM_H = 150, CAM_PAD = 16;
const CAM_ZONE = { x: BW - CAM_W - CAM_PAD - 10, y: CAM_PAD - 10, w: CAM_W + 30, h: CAM_H + 30 };

const PAPERS = [
  { bg: "linear-gradient(155deg,#f5e6d0,#ede0cc 40%,#e8d6be)", bd: "#c9b89a" },
  { bg: "linear-gradient(155deg,#f0f2f4,#e8eaed 40%,#eef0f2)", bd: "#c8ccd2" },
  { bg: "linear-gradient(155deg,#e8d5a3,#e0cc98 40%,#d9c48e)", bd: "#bfad7a" },
];

const TEXTURES = [
  () => (
    <>
      <div style={{
        position: "absolute", inset: 0, borderRadius: 2, pointerEvents: "none", opacity: .4,
        backgroundImage: `url("data:image/svg+xml,%3Csvg width='200' height='200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23g)' opacity='.035'/%3E%3C/svg%3E")`,
        backgroundSize: "200px 200px",
      }} />
      <div style={{
        position: "absolute", inset: 0, borderRadius: 2, pointerEvents: "none",
        background: "repeating-linear-gradient(0deg,transparent,transparent 2.5px,rgba(0,0,0,.006) 2.5px,rgba(0,0,0,.006) 3px)",
      }} />
    </>
  ),
  () => (
    <>
      <div style={{
        position: "absolute", inset: 0, borderRadius: 2, pointerEvents: "none",
        background: "radial-gradient(ellipse at 50% 50%,transparent 55%,rgba(160,130,80,.08) 100%)",
      }} />
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: "15%", borderRadius: "2px 2px 0 0", pointerEvents: "none",
        background: "linear-gradient(180deg,rgba(180,155,100,.06),transparent)",
      }} />
      <div style={{
        position: "absolute", bottom: 0, left: 0, right: 0, height: "15%", borderRadius: "0 0 2px 2px", pointerEvents: "none",
        background: "linear-gradient(0deg,rgba(140,115,70,.07),transparent)",
      }} />
    </>
  ),
  () => (
    <>
      <div style={{
        position: "absolute", top: "35%", left: 0, right: 0, height: 1, pointerEvents: "none",
        background: "linear-gradient(90deg,transparent 5%,rgba(0,0,0,.03) 20%,rgba(0,0,0,.045) 50%,rgba(0,0,0,.03) 80%,transparent 95%)",
      }} />
      <div style={{
        position: "absolute", top: 0, bottom: 0, left: "42%", width: 1, pointerEvents: "none",
        background: "linear-gradient(180deg,transparent 8%,rgba(0,0,0,.025) 25%,rgba(0,0,0,.04) 50%,rgba(0,0,0,.025) 75%,transparent 92%)",
      }} />
    </>
  ),
];

interface CurlDef { corner: "tl" | "tr" | "bl" | "br"; amt: number; }

const CurlOverlay = ({ curl }: { curl: CurlDef | null }) => {
  if (!curl) return null;
  const { corner: c, amt } = curl;
  const gDir = c === "bl" ? "to top right" : c === "br" ? "to top left" : c === "tl" ? "to bottom right" : "to bottom left";
  const pos: Record<string, number> = {};
  if (c.includes("t")) pos.top = 0; else pos.bottom = 0;
  if (c.includes("l")) pos.left = 0; else pos.right = 0;
  const br = c === "tl" ? "0 0 8px 0" : c === "tr" ? "0 0 0 8px" : c === "bl" ? "0 8px 0 0" : "8px 0 0 0";
  return (
    <div style={{
      position: "absolute", ...pos, width: amt * 5, height: amt * 5, pointerEvents: "none", zIndex: 3,
      borderRadius: br,
      background: `linear-gradient(${gDir},rgba(0,0,0,.06) 0%,rgba(0,0,0,.02) 40%,transparent 70%)`,
      boxShadow: `inset ${c.includes("r") ? "-" : ""}1px ${c.includes("b") ? "-" : ""}1px 3px rgba(0,0,0,.04)`,
    }} />
  );
};

const Shimmer = ({ pi }: { pi: number }) => {
  const bg = pi === 0 ? "rgba(120,90,50," : "rgba(100,100,110,";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "2px 0" }}>
      {[70, 50, 35].map((w, i) => (
        <div key={i} style={{
          height: 7, width: `${w}%`, borderRadius: 3,
          background: `linear-gradient(90deg,${bg}.04) 0%,${bg}.1) 50%,${bg}.04) 100%)`,
          backgroundSize: "300px 100%", animation: `sh 1.8s ease-in-out infinite`, animationDelay: `${i * .15}s`,
        }} />
      ))}
      {[88, 60].map((w, i) => (
        <div key={`b${i}`} style={{
          height: 5, width: `${w}%`, borderRadius: 3, marginTop: 3,
          background: `linear-gradient(90deg,${bg}.03) 0%,${bg}.08) 50%,${bg}.03) 100%)`,
          backgroundSize: "300px 100%", animation: `sh 1.8s ease-in-out infinite`, animationDelay: `${(i + 3) * .15}s`,
        }} />
      ))}
    </div>
  );
};

// Utility functions
function catenary(x1: number, y1: number, x2: number, y2: number) {
  const d = Math.hypot(x2 - x1, y2 - y1), sag = Math.min(d * .25, 80) + 25;
  return `M ${x1} ${y1} Q ${(x1 + x2) / 2} ${Math.max(y1, y2) + sag} ${x2} ${y2}`;
}

function inCamZone(x: number, y: number, w: number, h: number) {
  return !(x + w < CAM_ZONE.x || x > CAM_ZONE.x + CAM_ZONE.w || y + h < CAM_ZONE.y || y > CAM_ZONE.y + CAM_ZONE.h);
}

interface PositionedSource extends IntelSource {
  id: string;
  x: number;
  y: number;
  loading: boolean;
  pi: number;
  ti: number;
  rot: number;
  curl: CurlDef | null;
  appeared: boolean;
}

function randPos(ex: PositionedSource[], bp: { x: number; y: number } | null) {
  const m = 30;
  for (let i = 0; i < 120; i++) {
    const x = m + Math.random() * (BW - GW - m * 2), y = 50 + Math.random() * (BH - GH - 85);
    if (inCamZone(x, y, GW, GH)) continue;
    let ok = true;
    if (bp && Math.abs(bp.x + BDW / 2 - x - GW / 2) < (BDW + GW) / 2 + 20 && Math.abs(bp.y + BDH / 2 - y - GH / 2) < (BDH + GH) / 2 + 20) ok = false;
    for (const d of ex) if (Math.abs(d.x - x) < GW + 12 && Math.abs(d.y - y) < GH + 12) { ok = false; break; }
    if (ok) return { x, y };
  }
  return { x: m + Math.random() * (BW - GW - m * 2), y: 180 + Math.random() * (BH - GH - 220) };
}

function genCurl(): CurlDef | null {
  if (Math.random() < 0.45) return null;
  const c = ["tl", "tr", "bl", "br"] as const;
  return { corner: c[Math.floor(Math.random() * 4)], amt: 2 + Math.random() * 5 };
}

interface BoardData {
  blu: { x: number; y: number } | null;
  srcs: PositionedSource[];
}

function buildBoardData(person: IntelPerson): BoardData {
  if (!person || !person.sources.length) return { blu: null, srcs: [] };
  const blu = { x: BW / 2 - BDW / 2 - 40, y: BH / 2 - BDH / 2 - 10 };
  const srcs: PositionedSource[] = [];
  person.sources.forEach((s, i) => {
    const pos = randPos(srcs, blu);
    srcs.push({
      ...s, id: `${person.id}-s${i}`, ...pos,
      pi: i % 3, ti: i % 3, rot: (Math.random() - .5) * 4, curl: genCurl(), appeared: false, loading: false,
    });
  });
  return { blu, srcs };
}

interface SelDoc {
  kind: "summary" | "source";
  id?: string;
  nm?: string;
  tp?: string;
  sn?: string;
}

export default function IntelBoard() {
  /*
   * STATE MANAGEMENT
   * - people: array of all scanned persons (from Browser Use agents)
   * - activePerson: currently selected person shown on board
   * - boardData: positioned documents for the active person
   * - boardFade: controls crossfade transition (true = visible)
   */
  const [people] = useState<IntelPerson[]>(demoPeople);
  const [activePerson, setActivePerson] = useState<IntelPerson | null>(null);
  const [boardData, setBoardData] = useState<BoardData>({ blu: null, srcs: [] });
  const [boardFade, setBoardFade] = useState(true);
  const [search, setSearch] = useState("");

  const [tier, setTier] = useState(2);
  const [selDoc, setSelDoc] = useState<SelDoc | null>(null);
  const [modalVis, setModalVis] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [vsc, setVsc] = useState(1);
  const [camConnected] = useState(false);
  const drag = useRef({ sx: 0, sy: 0, dx: 0, dy: 0, moved: false, id: null as string | null });
  const vscRef = useRef(1);

  useEffect(() => {
    const fn = () => {
      const availW = window.innerWidth - SIDE_W - 40;
      const s = Math.min(availW / (BW + FR * 2), (window.innerHeight - 60) / (BH + FR * 2), 1);
      vscRef.current = s; setVsc(s);
    };
    fn(); window.addEventListener("resize", fn); return () => window.removeEventListener("resize", fn);
  }, []);

  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === "Escape" && tier === 3) backFromDoc(); };
    window.addEventListener("keydown", fn); return () => window.removeEventListener("keydown", fn);
  }, [tier]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const d = drag.current; if (!d.id) return;
      const sc = vscRef.current * ZM[1];
      const mx = (e.clientX - d.sx) / sc, my = (e.clientY - d.sy) / sc;
      if (!d.moved && Math.hypot(mx, my) < 4) return;
      if (!d.moved) { d.moved = true; setDragId(d.id); }
      if (d.id === "blue") {
        setBoardData(prev => ({
          ...prev, blu: {
            x: Math.max(0, Math.min(BW - BDW, d.dx + mx)),
            y: Math.max(0, Math.min(BH - BDH, d.dy + my)),
          },
        }));
      } else {
        setBoardData(prev => ({
          ...prev, srcs: prev.srcs.map(s => s.id === d.id ? {
            ...s,
            x: Math.max(0, Math.min(BW - GW, d.dx + mx)),
            y: Math.max(0, Math.min(BH - GH, d.dy + my)),
          } : s),
        }));
      }
    };
    const onUp = () => { drag.current.id = null; setDragId(null); };
    window.addEventListener("mousemove", onMove); window.addEventListener("mouseup", onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, []);

  /*
   * SELECT PERSON — Crossfade transition
   * 1. Fade out current board (boardFade -> false)
   * 2. After fade-out, swap data and fade in (boardFade -> true)
   *
   * In real implementation:
   * - Load person's sources from memory/storage layer
   * - If person has no cached board positions, generate them
   * - If person is "scanning", show sources as they arrive
   */
  const selectPerson = useCallback((p: IntelPerson) => {
    if (activePerson?.id === p.id) return;
    setBoardFade(false);
    setTimeout(() => {
      setActivePerson(p);
      const data = buildBoardData(p);
      setBoardData(data);
      setBoardFade(true);
      // Trigger appear animation for each source
      setTimeout(() => {
        setBoardData(prev => ({ ...prev, srcs: prev.srcs.map(s => ({ ...s, appeared: true })) }));
      }, 50);
    }, 400);
  }, [activePerson]);

  const clickDoc = (d: SelDoc) => {
    if (drag.current.moved || tier !== 2) return;
    drag.current.moved = false;
    setSelDoc(d); setTier(3);
    setTimeout(() => setModalVis(true), 800);
  };

  const backFromDoc = () => {
    setModalVis(false);
    setTimeout(() => { setSelDoc(null); setTier(2); }, 280);
  };

  const startDrag = (e: React.MouseEvent, id: string, x: number, y: number) => {
    if (tier !== 2) return; e.preventDefault();
    drag.current = { sx: e.clientX, sy: e.clientY, dx: x, dy: y, moved: false, id };
  };

  const { blu, srcs } = boardData;
  const bpx = blu ? blu.x + BDW / 2 : 0, bpy = blu ? blu.y + 8 : 0;

  const cam = (() => {
    const s = vsc;
    if (tier === 2) return `scale(${s * ZM[1]})`;
    if (tier === 3 && selDoc) {
      let cx, cy;
      if (selDoc.kind === "summary" && blu) { cx = blu.x + BDW / 2 - BW / 2; cy = blu.y + BDH / 2 - BH / 2; }
      else { const f = srcs.find(x => x.id === selDoc.id); if (!f) return `scale(${s})`; cx = f.x + GW / 2 - BW / 2; cy = f.y + GH / 2 - BH / 2; }
      return `scale(${s * ZM[2]}) translate(${-cx!}px,${-cy!}px)`;
    }
    return `scale(${s})`;
  })();

  return (
    <div style={{
      width: "100vw", height: "100vh", overflow: "hidden", position: "relative",
      fontFamily: "'Inter',system-ui,sans-serif", display: "flex",
      background: "linear-gradient(180deg,#070b14 0%,#0a0f1c 25%,#0d1224 50%,#0f1628 75%,#111828 100%)",
    }}>
      <style>{`
        @keyframes sh{0%{background-position:-150px 0}100%{background-position:150px 0}}
        @keyframes fi{0%{opacity:0;transform:scale(.78)}100%{opacity:1;transform:scale(1)}}
        @keyframes sm{0%{transform:translateY(-100%)}100%{transform:translateY(100%)}}
        @keyframes pf{0%{transform:translateY(0);opacity:0}15%{opacity:.3}85%{opacity:.3}100%{transform:translateY(-140px);opacity:0}}
        @keyframes mi{0%{opacity:0;transform:scale(.93) translateY(12px)}100%{opacity:1;transform:scale(1) translateY(0)}}
        @keyframes dl{0%{stroke-dashoffset:600}100%{stroke-dashoffset:0}}
        @keyframes fl{0%,94%,100%{opacity:1}95%{opacity:.6}97%{opacity:1}98%{opacity:.5}}
        @keyframes camPulse{0%,100%{opacity:1;box-shadow:0 0 6px rgba(74,222,128,.6)}50%{opacity:.55;box-shadow:0 0 3px rgba(74,222,128,.3)}}
        @keyframes staticFlicker{0%{background-position:0 0}33%{background-position:50px 30px}66%{background-position:20px 60px}100%{background-position:70px 10px}}
        @keyframes scanPulse{0%,100%{opacity:1}50%{opacity:.4}}
        @keyframes listSlideIn{0%{opacity:0;transform:translateY(-8px)}100%{opacity:1;transform:translateY(0)}}
      `}</style>

      {/* Wall texture */}
      <div style={{
        position: "fixed", inset: 0, pointerEvents: "none",
        backgroundImage: "radial-gradient(circle,rgba(255,255,255,.006) 1px,transparent 1px)", backgroundSize: "20px 20px",
      }} />

      {/* LEFT SIDEBAR */}
      <Sidebar
        people={people}
        activePerson={activePerson}
        onSelect={selectPerson}
        search={search}
        setSearch={setSearch}
      />

      {/* BOARD AREA */}
      <div style={{ flex: 1, position: "relative", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>

        {/* Environment details */}
        <div style={{
          position: "absolute", right: 20, top: 0, bottom: 0, width: 3,
          background: "linear-gradient(180deg,#141c28,#0f1520,#141c28)",
          borderRight: "1px solid #1e2638", opacity: .3, pointerEvents: "none",
        }} />
        <div style={{
          position: "absolute", bottom: 0, left: 0, right: 0, height: 80, pointerEvents: "none",
          background: "linear-gradient(180deg,transparent,rgba(3,5,10,.5))",
        }} />

        {/* CAMERA WRAPPER */}
        <div style={{
          width: BW + FR * 2, height: BH + FR * 2, position: "relative",
          transform: cam, transformOrigin: "center center",
          transition: tier === 3 ? "transform 0.85s cubic-bezier(.25,.46,.45,.94)" : "transform 1s cubic-bezier(.25,.46,.45,.94)",
        }}>

          {/* Fluorescent light */}
          <div style={{
            position: "absolute", top: -58, left: "50%", transform: "translateX(-50%)", width: 300, height: 14, zIndex: 30,
            background: "linear-gradient(180deg,#1a2232,#222d3e)", borderRadius: 3, border: "1px solid #2a3445",
          }}>
            <div style={{
              position: "absolute", bottom: -3, left: 16, right: 16, height: 7,
              background: "linear-gradient(180deg,#dce4f0,#c8d2e2)", borderRadius: 3, animation: "fl 10s infinite",
              boxShadow: "0 0 30px rgba(200,215,240,.2),0 0 80px rgba(180,200,230,.1)",
            }} />
          </div>
          <div style={{
            position: "absolute", top: -40, left: "50%", transform: "translateX(-50%)",
            width: 500, height: 180, pointerEvents: "none", zIndex: 0,
            background: "radial-gradient(ellipse at top center,rgba(180,200,230,.04) 0%,transparent 70%)",
          }} />

          {/* BOARD FRAME */}
          <div style={{
            position: "absolute", inset: 0, zIndex: 2,
            background: "linear-gradient(145deg,#1a2235,#141c2a,#1e2840)", borderRadius: 6,
            border: "1px solid #2a3448",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,.04),0 10px 50px rgba(0,0,0,.6),0 2px 8px rgba(0,0,0,.3)",
          }}>
            {[{ top: 9, left: 9 }, { top: 9, right: 9 }, { bottom: 9, right: 9 }, { bottom: 9, left: 9 }].map((p, i) => (
              <div key={i} style={{
                position: "absolute", width: 13, height: 13, borderRadius: "50%", ...p,
                background: "radial-gradient(circle at 40% 35%,#6a7080,#3a4250,#2a3040)",
                border: "1px solid #4a5260", zIndex: 3,
                boxShadow: "inset 0 1px 2px rgba(255,255,255,.1),0 1px 3px rgba(0,0,0,.5)",
              }}>
                <div style={{
                  position: "absolute", top: 3, left: 3, width: 2, height: 5,
                  background: "rgba(255,255,255,.08)", borderRadius: 1, transform: "rotate(-30deg)",
                }} />
              </div>
            ))}
          </div>

          {/* BOARD SURFACE */}
          <div style={{
            position: "absolute", top: FR, left: FR, right: FR, bottom: FR, zIndex: 4,
            background: "linear-gradient(155deg,#0d1321 0%,#0a0f1a 35%,#0f1629 70%,#111827 100%)", borderRadius: 2,
          }}>
            <div style={{ position: "absolute", inset: 0, overflow: "hidden", borderRadius: 2, pointerEvents: "none", zIndex: 1 }}>
              <div style={{
                position: "absolute", width: "100%", height: "200%", opacity: .025,
                background: "repeating-linear-gradient(0deg,transparent 0px,transparent 3px,rgba(148,163,184,.4) 3px,rgba(148,163,184,.4) 4px)",
                animation: "sm 12s linear infinite",
              }} />
            </div>
            <div style={{
              position: "absolute", inset: 0, pointerEvents: "none", opacity: .02, borderRadius: 2,
              backgroundImage: "radial-gradient(circle,#475569 1px,transparent 1px)", backgroundSize: "26px 26px",
            }} />
            <div style={{
              position: "absolute", inset: 0, pointerEvents: "none", zIndex: 2, borderRadius: 2,
              background: "radial-gradient(ellipse at center,transparent 45%,rgba(3,6,16,.55) 100%)",
            }} />
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} style={{
                position: "absolute", left: `${10 + Math.random() * 80}%`, bottom: `${Math.random() * 15}%`,
                width: 1.5, height: 1.5, borderRadius: "50%", background: "rgba(148,163,184,.2)",
                animation: `pf ${8 + Math.random() * 8}s linear infinite`, animationDelay: `${Math.random() * 8}s`,
                pointerEvents: "none", zIndex: 2,
              }} />
            ))}
          </div>

          {/* Camera feed */}
          <CameraFeed connected={camConnected} />

          {/* BOARD CONTENT — Crossfade wrapper */}
          <div style={{
            position: "absolute", top: FR, left: FR, width: BW, height: BH, zIndex: 10,
            opacity: boardFade ? 1 : 0, transition: "opacity .4s ease",
          }}>

            {/* SVG strings */}
            <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 8 }}>
              {blu && srcs.map(s => (
                <g key={s.id}>
                  <path d={catenary(s.x + GW / 2, s.y + 4, bpx, bpy)} fill="none" stroke="rgba(140,20,20,.08)" strokeWidth={5} />
                  <path d={catenary(s.x + GW / 2, s.y + 4, bpx, bpy)} fill="none" stroke="#b91c1c" strokeWidth={1.4} opacity={.55}
                    strokeDasharray="600" style={{ animation: "dl 1.5s ease-out forwards" }} />
                </g>
              ))}
            </svg>

            {/* BLUE SUMMARY DOC */}
            {blu && activePerson && (
              <div
                onMouseDown={e => startDrag(e, "blue", blu.x, blu.y)}
                onClick={() => clickDoc({ kind: "summary" })}
                style={{
                  position: "absolute", left: blu.x, top: blu.y, width: BDW, height: BDH,
                  background: PAPERS[1].bg, border: `1px solid ${PAPERS[1].bd}`, borderRadius: 2,
                  padding: "14px 14px 14px",
                  cursor: tier === 2 ? (dragId === "blue" ? "grabbing" : "grab") : "pointer",
                  zIndex: dragId === "blue" ? 32 : 22, animation: "fi .7s ease-out",
                  transform: dragId === "blue" ? "scale(1.04)" : "scale(1)",
                  boxShadow: dragId === "blue"
                    ? "0 16px 45px rgba(0,0,0,.45),0 2px 6px rgba(0,0,0,.2)"
                    : "0 4px 14px rgba(0,0,0,.35),0 1px 3px rgba(0,0,0,.15)",
                  transition: "box-shadow .2s,transform .2s",
                }}
              >
                {TEXTURES[1]()}
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, position: "relative", zIndex: 1 }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: "50%", flexShrink: 0,
                    background: "linear-gradient(135deg,#d0d5dd,#b8bfc8)", border: "2px solid #a0a8b4",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="8" r="4" fill="#6b7280" />
                      <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" fill="#6b7280" />
                    </svg>
                  </div>
                  <div>
                    <div style={{ color: "#111827", fontSize: 12, fontWeight: 700, letterSpacing: ".04em" }}>{activePerson.summary.nm}</div>
                    <div style={{ color: "#dc2626", fontSize: 9, fontWeight: 600, letterSpacing: ".06em", marginTop: 1 }}>
                      {srcs.length} SOURCE{srcs.length !== 1 ? "S" : ""} FOUND
                    </div>
                  </div>
                </div>
                <div style={{
                  color: "#4b5563", fontSize: 9, lineHeight: 1.45, overflow: "hidden", position: "relative", zIndex: 1,
                  textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                }}>
                  {activePerson.summary.sm}
                </div>
              </div>
            )}

            {/* SOURCE DOCS */}
            {srcs.map(s => {
              const p = PAPERS[s.pi], isD = dragId === s.id;
              return (
                <div
                  key={s.id}
                  onMouseDown={e => !s.loading && startDrag(e, s.id, s.x, s.y)}
                  onClick={() => !s.loading && clickDoc({ kind: "source", id: s.id, nm: s.nm, tp: s.tp, sn: s.sn })}
                  style={{
                    position: "absolute", left: s.x, top: s.y, width: GW, height: GH,
                    background: p.bg, border: `1px solid ${p.bd}`, borderRadius: 2,
                    padding: "14px 11px 10px",
                    cursor: s.loading ? "default" : tier === 2 ? (isD ? "grabbing" : "grab") : "pointer",
                    zIndex: isD ? 32 : 14,
                    opacity: s.appeared ? 1 : 0,
                    transform: `rotate(${s.appeared ? s.rot : 0}deg) scale(${isD ? 1.06 : s.appeared ? 1 : 0.8})`,
                    boxShadow: isD
                      ? "0 18px 45px rgba(0,0,0,.45),0 2px 6px rgba(0,0,0,.2)"
                      : "0 3px 10px rgba(0,0,0,.3),0 1px 2px rgba(0,0,0,.12)",
                    transition: "box-shadow .2s,transform .8s ease-out,opacity .8s ease-out",
                  }}
                >
                  {TEXTURES[s.ti]()}
                  <CurlOverlay curl={s.curl} />
                  {s.loading ? <Shimmer pi={s.pi} /> : (
                    <div style={{ position: "relative", zIndex: 1 }}>
                      <div style={{ marginBottom: 5 }}>
                        <span style={{
                          color: "#065f46", fontSize: 7, fontWeight: 700, letterSpacing: ".1em",
                          background: "rgba(5,150,105,.06)", padding: "2px 5px", borderRadius: 2,
                          border: "1px solid rgba(5,150,105,.12)",
                        }}>{s.tp}</span>
                      </div>
                      <div style={{ color: "#111827", fontSize: 10.5, fontWeight: 650, marginBottom: 4 }}>{s.nm}</div>
                      <div style={{
                        color: "#4b5563", fontSize: 8.5, lineHeight: 1.4, overflow: "hidden",
                        textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                      }}>{s.sn}</div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* BACK BUTTON */}
        {tier === 3 && (
          <button onClick={backFromDoc} style={{
            position: "fixed", top: 20, left: SIDE_W + 20, zIndex: 60,
            padding: "8px 18px", background: "rgba(255,255,255,.06)",
            border: "1px solid rgba(255,255,255,.1)", borderRadius: 6,
            color: "#94a3b8", fontSize: 12, fontWeight: 600, cursor: "pointer",
            backdropFilter: "blur(8px)", display: "flex", alignItems: "center", gap: 6,
          }}>
            <span style={{ fontSize: 14 }}>←</span> Back
          </button>
        )}
      </div>

      {/* GLASSMORPHISM MODAL */}
      {modalVis && selDoc && (
        <div onClick={backFromDoc} style={{
          position: "fixed", inset: 0, zIndex: 100,
          background: "rgba(3,6,16,.5)", backdropFilter: "blur(10px)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            width: 540, maxHeight: "80vh", overflowY: "auto",
            background: selDoc.kind === "summary"
              ? "linear-gradient(140deg,rgba(15,25,50,.92),rgba(30,58,95,.8))"
              : "linear-gradient(140deg,rgba(10,30,22,.92),rgba(18,48,32,.8))",
            backdropFilter: "blur(40px)",
            border: `1px solid ${selDoc.kind === "summary" ? "rgba(96,165,250,.2)" : "rgba(52,211,153,.2)"}`,
            borderRadius: 14, padding: "26px 30px 30px",
            boxShadow: "0 30px 80px rgba(0,0,0,.5)", animation: "mi .35s ease-out",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div style={{
                color: selDoc.kind === "summary" ? "#60a5fa" : "#34d399",
                fontSize: 9, fontWeight: 700, letterSpacing: ".14em",
                background: selDoc.kind === "summary" ? "rgba(96,165,250,.08)" : "rgba(52,211,153,.08)",
                padding: "4px 10px", borderRadius: 3,
                border: `1px solid ${selDoc.kind === "summary" ? "rgba(96,165,250,.18)" : "rgba(52,211,153,.18)"}`,
              }}>
                {selDoc.kind === "summary" ? "INTELLIGENCE SUMMARY" : selDoc.tp}
              </div>
              <button onClick={backFromDoc} style={{
                background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.08)", color: "#7a8a9a",
                width: 28, height: 28, borderRadius: 6, cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12,
              }}>✕</button>
            </div>
            {selDoc.kind === "summary" && activePerson ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
                  <div style={{
                    width: 58, height: 58, borderRadius: "50%", flexShrink: 0,
                    background: "linear-gradient(135deg,#1e3a5f,rgba(37,99,235,.2))",
                    border: "2px solid #2d4a6f", display: "flex", alignItems: "center", justifyContent: "center",
                  }}>
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="8" r="4" fill="#64748b" />
                      <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" fill="#64748b" />
                    </svg>
                  </div>
                  <div>
                    <div style={{ color: "#f1f5f9", fontSize: 20, fontWeight: 700 }}>{activePerson.summary.nm}</div>
                    <div style={{ color: "#60a5fa", fontSize: 11.5, fontWeight: 600, marginTop: 2 }}>
                      {srcs.length} SOURCE{srcs.length !== 1 ? "S" : ""} AGGREGATED
                    </div>
                  </div>
                </div>
                <div style={{ height: 1, background: "linear-gradient(90deg,transparent,rgba(96,165,250,.15),transparent)", marginBottom: 16 }} />
                <div style={{ color: "#b8c8d8", fontSize: 13.5, lineHeight: 1.75 }}>{activePerson.summary.sm}</div>
              </>
            ) : (
              <>
                <div style={{ color: "#f1f5f9", fontSize: 18, fontWeight: 700 }}>{selDoc.nm}</div>
                <div style={{ height: 1, background: "linear-gradient(90deg,transparent,rgba(52,211,153,.15),transparent)", margin: "14px 0" }} />
                <div style={{ color: "#b8c8d8", fontSize: 13.5, lineHeight: 1.75 }}>{selDoc.sn}</div>
              </>
            )}
            <div style={{
              height: 1, background: `linear-gradient(90deg,transparent,${selDoc.kind === "summary" ? "rgba(96,165,250,.12)" : "rgba(52,211,153,.12)"},transparent)`,
              marginTop: 24,
            }} />
            <div style={{ marginTop: 12, color: "#3a4a5a", fontSize: 9, letterSpacing: ".12em", textAlign: "center", fontWeight: 600 }}>
              CLASSIFIED • EYES ONLY • {new Date().toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }).toUpperCase()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
