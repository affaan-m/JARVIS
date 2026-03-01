"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { demoPeople } from "@/lib/demo-data";
import type { Dossier, IntelPerson, IntelSource, IntelSourceSessionStatus } from "@/lib/types";
import { useFrameCapture } from "@/lib/useFrameCapture";
import { useGlassesStream } from "@/lib/useGlassesStream";
import { useResearchStream } from "@/lib/useResearchStream";
import { useVoiceCommands } from "@/lib/useVoiceCommands";
import { BrowserSessionViewer } from "./BrowserSessionViewer";
import { CameraFeed } from "./CameraFeed";
import { Sidebar } from "./Sidebar";
import { StatusBar } from "./StatusBar";
import { TopBar } from "./TopBar";

/*
 * ============================================================
 * INTELLIGENCE CORKBOARD — v6
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
 * 3. SUMMARY DOCUMENT (center doc):
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

const BW = 1100, BH = 680, GW = 168, GH = 108, BDW = 220, BDH = 200, FR = 0, SIDE_W = 270;
const ZM = [0.48, 1, 1.65];
const CAM_W = 380, CAM_H = 240, CAM_PAD = 16;
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

function clampOutOfCamZone(x: number, y: number, w: number, h: number) {
  if (!inCamZone(x, y, w, h)) return { x, y };
  // Find shortest escape: left, right, up, down
  const escL = CAM_ZONE.x - (x + w);       // push left so card's right edge clears zone left
  const escR = (CAM_ZONE.x + CAM_ZONE.w) - x; // push right so card's left edge clears zone right
  const escU = CAM_ZONE.y - (y + h);        // push up so card's bottom clears zone top
  const escD = (CAM_ZONE.y + CAM_ZONE.h) - y;  // push down so card's top clears zone bottom
  const moves: { dx: number; dy: number; dist: number }[] = [
    { dx: escL, dy: 0, dist: Math.abs(escL) },
    { dx: escR, dy: 0, dist: Math.abs(escR) },
    { dx: 0, dy: escU, dist: Math.abs(escU) },
    { dx: 0, dy: escD, dist: Math.abs(escD) },
  ];
  // Filter out moves that push outside board bounds
  const valid = moves.filter(m => {
    const nx = x + m.dx, ny = y + m.dy;
    return nx >= 0 && nx + w <= BW && ny >= 0 && ny + h <= BH;
  });
  const best = (valid.length ? valid : moves).sort((a, b) => a.dist - b.dist)[0];
  return {
    x: Math.max(0, Math.min(BW - w, x + best.dx)),
    y: Math.max(0, Math.min(BH - h, y + best.dy)),
  };
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
  const fx = m + Math.random() * (BW - GW - m * 2), fy = 180 + Math.random() * (BH - GH - 220);
  if (inCamZone(fx, fy, GW, GH)) return { x: Math.min(fx, CAM_ZONE.x - GW - 10), y: fy };
  return { x: fx, y: fy };
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
      pi: i % 3, ti: i % 3, rot: (Math.random() - .5) * 8, curl: genCurl(), appeared: false, loading: false,
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
  sessionId?: string;
  liveUrl?: string;
  shareUrl?: string;
  sessionStatus?: IntelSourceSessionStatus;
}

const SH = { fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, letterSpacing: ".18em", color: "#52525b", marginBottom: 8, textTransform: "uppercase" as const };
const PILL = { display: "inline-block", padding: "3px 8px", borderRadius: 3, background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.06)", fontSize: 11, color: "#d4d4d8", marginRight: 6, marginBottom: 4 };

function DossierModal({ person }: { person: IntelPerson }) {
  const d = person.dossier;
  return (
    <div style={{ position: "relative", zIndex: 1 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 12 }}>
        <div style={{
          width: 48, height: 48, borderRadius: "50%", flexShrink: 0,
          background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.07)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="8" r="4" fill="#52525b" />
            <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" fill="#52525b" />
          </svg>
        </div>
        <div>
          <div style={{ color: "#f4f4f5", fontSize: 18, fontWeight: 700, letterSpacing: ".04em" }}>
            {person.summary.nm}
          </div>
          {(d?.title || d?.company) && (
            <div style={{ color: "#71717a", fontSize: 11, marginTop: 2 }}>
              {d.title}{d.title && d.company ? " · " : ""}{d.company}
            </div>
          )}
        </div>
      </div>

      <div style={{ height: 1, background: "rgba(255,255,255,.07)", marginBottom: 14 }} />

      {/* Summary */}
      <div style={{ color: "#a1a1aa", fontSize: 13, lineHeight: 1.75, marginBottom: 18 }}>
        {d?.summary || person.summary.sm}
      </div>

      {/* Social Links */}
      {d?.socialProfiles && Object.keys(d.socialProfiles).length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={SH}>SOCIAL PROFILES</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {Object.entries(d.socialProfiles).map(([platform, url]) => url ? (
              <a key={platform} href={url} target="_blank" rel="noopener noreferrer"
                style={{ ...PILL, color: "#818cf8", textDecoration: "none", cursor: "pointer" }}>
                {platform}
              </a>
            ) : null)}
          </div>
        </div>
      )}

      {/* Work History */}
      {d?.workHistory && d.workHistory.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={SH}>WORK HISTORY</div>
          {d.workHistory.map((w, i) => (
            <div key={i} style={{ marginBottom: 8, paddingLeft: 10, borderLeft: "2px solid rgba(255,255,255,.06)" }}>
              <div style={{ color: "#e4e4e7", fontSize: 12, fontWeight: 600 }}>{w.role}</div>
              <div style={{ color: "#71717a", fontSize: 11 }}>
                {w.company}{w.period ? ` · ${w.period}` : ""}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Education */}
      {d?.education && d.education.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={SH}>EDUCATION</div>
          {d.education.map((e, i) => (
            <div key={i} style={{ marginBottom: 6, paddingLeft: 10, borderLeft: "2px solid rgba(255,255,255,.06)" }}>
              <div style={{ color: "#e4e4e7", fontSize: 12, fontWeight: 600 }}>{e.school}</div>
              {e.degree && <div style={{ color: "#71717a", fontSize: 11 }}>{e.degree}</div>}
            </div>
          ))}
        </div>
      )}

      {/* Notable Activity */}
      {d?.notableActivity && d.notableActivity.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={SH}>NOTABLE ACTIVITY</div>
          <ul style={{ margin: 0, paddingLeft: 16, color: "#a1a1aa", fontSize: 12, lineHeight: 1.7 }}>
            {d.notableActivity.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </div>
      )}

      {/* Conversation Hooks */}
      {d?.conversationHooks && d.conversationHooks.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={SH}>CONVERSATION HOOKS</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {d.conversationHooks.map((h, i) => (
              <span key={i} style={{ ...PILL, background: "rgba(74,222,128,.06)", border: "1px solid rgba(74,222,128,.12)", color: "#86efac" }}>
                {h}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Risk Flags */}
      {d?.riskFlags && d.riskFlags.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ ...SH, color: "#ef4444" }}>RISK FLAGS</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {d.riskFlags.map((r, i) => (
              <span key={i} style={{ ...PILL, background: "rgba(239,68,68,.08)", border: "1px solid rgba(239,68,68,.15)", color: "#fca5a5" }}>
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Sources count */}
      <div style={{ height: 1, background: "rgba(255,255,255,.07)", marginTop: 8, marginBottom: 10 }} />
      <div style={{ color: "#52525b", fontSize: 10, fontFamily: "monospace", letterSpacing: ".08em" }}>
        {person.sources.length} INTELLIGENCE SOURCE{person.sources.length !== 1 ? "S" : ""} COLLECTED
      </div>
    </div>
  );
}

export default function IntelBoard() {
  /*
   * STATE MANAGEMENT
   * - people: array of all scanned persons (from Browser Use agents)
   * - activePerson: currently selected person shown on board
   * - boardData: positioned documents for the active person
   * - boardFade: controls crossfade transition (true = visible)
   */
  // Research stream for live SSE data
  const {
    isStreaming,
    person: streamPerson,
    liveSessionId,
    liveUrl: streamLiveUrl,
    startStream,
    totalSources,
  } = useResearchStream();

  // Merge streamed person into people list
  const [people, setPeople] = useState<IntelPerson[]>(demoPeople);
  const [activePerson, setActivePerson] = useState<IntelPerson | null>(null);
  const [boardData, setBoardData] = useState<BoardData>({ blu: null, srcs: [] });
  const [boardFade, setBoardFade] = useState(true);
  const [search, setSearch] = useState("");

  // When streamPerson updates, merge into people list + APPEND new sources (don't rebuild)
  const prevSourceCountRef = useRef(0);
  useEffect(() => {
    if (!streamPerson) return;

    // If the X session has a liveUrl, inject it into the first Twitter/X source
    const enrichedPerson: IntelPerson = {
      ...streamPerson,
      sources: streamPerson.sources.map((s) => {
        if ((s.nm.includes("Twitter") || s.nm.includes("X Activity")) && liveSessionId) {
          return { ...s, sessionId: liveSessionId, liveUrl: streamLiveUrl ?? undefined, sessionStatus: "running" as const };
        }
        return s;
      }),
    };

    setPeople((prev) => {
      const existing = prev.findIndex((p) => p.id === enrichedPerson.id);
      if (existing >= 0) {
        const updated = [...prev];
        updated[existing] = enrichedPerson;
        return updated;
      }
      return [enrichedPerson, ...prev];
    });

    setActivePerson(enrichedPerson);

    // Only add NEW sources to the board — don't rebuild existing positions
    const prevCount = prevSourceCountRef.current;
    const newSources = enrichedPerson.sources.slice(prevCount);
    prevSourceCountRef.current = enrichedPerson.sources.length;

    if (prevCount === 0 && newSources.length > 0) {
      // First source: create the blue summary doc + first source
      const blu = { x: BW / 2 - BDW / 2 - 40, y: BH / 2 - BDH / 2 - 10 };
      const srcs: PositionedSource[] = [];
      newSources.forEach((s, i) => {
        const pos = randPos(srcs, blu);
        srcs.push({
          ...s, id: `${enrichedPerson.id}-s${i}`, ...pos,
          pi: i % 3, ti: i % 3, rot: (Math.random() - .5) * 8, curl: genCurl(), appeared: false, loading: false,
        });
      });
      setBoardData({ blu, srcs });
      setBoardFade(true);
      setTimeout(() => {
        setBoardData((prev) => ({ ...prev, srcs: prev.srcs.map((s) => ({ ...s, appeared: true })) }));
      }, 50);
    } else if (newSources.length > 0) {
      // Append new sources to existing board layout
      setBoardData((prev) => {
        const existingSrcs = prev.srcs;
        const appended: PositionedSource[] = [];
        newSources.forEach((s, i) => {
          const idx = prevCount + i;
          const pos = randPos([...existingSrcs, ...appended], prev.blu);
          appended.push({
            ...s, id: `${enrichedPerson.id}-s${idx}`, ...pos,
            pi: idx % 3, ti: idx % 3, rot: (Math.random() - .5) * 8, curl: genCurl(), appeared: false, loading: false,
          });
        });
        return { ...prev, srcs: [...existingSrcs, ...appended] };
      });
      // Animate new sources in
      setTimeout(() => {
        setBoardData((prev) => ({ ...prev, srcs: prev.srcs.map((s) => ({ ...s, appeared: true })) }));
      }, 50);
    }
  }, [streamPerson, liveSessionId, streamLiveUrl]);

  // Search handler: pressing Enter on a name triggers live research
  const handleSearchSubmit = useCallback(() => {
    const name = search.trim();
    if (!name || isStreaming) return;
    prevSourceCountRef.current = 0; // Reset for new stream
    startStream(name);
    setSearch("");
  }, [search, isStreaming, startStream]);

  const [tier, setTier] = useState(2);
  const [selDoc, setSelDoc] = useState<SelDoc | null>(null);
  const [modalVis, setModalVis] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [vsc, setVsc] = useState(1);
  const {
    videoRef, status: camStatus, connect: camConnect, connectWebcam: camWebcam, disconnect: camDisconnect, error: camError,
  } = useGlassesStream();
  const [detectionCount, setDetectionCount] = useState<number | undefined>(undefined);

  // Pipeline status for visual feedback overlay
  type PipelineStatus =
    | { stage: "idle" }
    | { stage: "scanning" }
    | { stage: "detected"; count: number }
    | { stage: "identifying"; trackId: number }
    | { stage: "identified"; name: string }
    | { stage: "researching"; name: string };
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>({ stage: "idle" });

  const identifiedRef = useRef<Set<string>>(new Set());
  useFrameCapture({
    videoRef,
    enabled: camStatus === "live",
    onCapture: (res) => {
      setDetectionCount(res.detections.length);

      // Update pipeline status based on frame response
      if (res.new_persons > 0) {
        setPipelineStatus({ stage: "detected", count: res.new_persons });
      }

      // Check identification statuses
      if (res.identifications) {
        for (const ident of res.identifications) {
          if (ident.status === "identifying") {
            setPipelineStatus({ stage: "identifying", trackId: ident.track_id });
          }
          if (ident.status === "identified" && ident.name && !identifiedRef.current.has(ident.name)) {
            identifiedRef.current.add(ident.name);
            setPipelineStatus({ stage: "identified", name: ident.name });
            if (!isStreaming) {
              // Brief delay so user sees the "IDENTIFIED" state before research starts
              setTimeout(() => {
                setPipelineStatus({ stage: "researching", name: ident.name! });
                prevSourceCountRef.current = 0;
                startStream(ident.name!);
              }, 1200);
            }
          }
        }
      }
    },
  });

  // Set pipeline to "scanning" when camera goes live
  useEffect(() => {
    if (camStatus === "live" && pipelineStatus.stage === "idle") {
      setPipelineStatus({ stage: "scanning" });
    }
    if (camStatus === "disconnected") {
      setPipelineStatus({ stage: "idle" });
    }
  }, [camStatus, pipelineStatus.stage]);

  // When streaming starts via sidebar search, update pipeline
  useEffect(() => {
    if (isStreaming && streamPerson) {
      setPipelineStatus({ stage: "researching", name: streamPerson.summary.nm });
    }
  }, [isStreaming, streamPerson]);

  // ─── Voice Commands via Web Speech API ───
  // "target" / "scan" → capture current frame & trigger face ID pipeline
  // "research <name>" → skip face ID, go straight to SSE research
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [lastTranscript, setLastTranscript] = useState<string | null>(null);

  // Capture-now: grab a single frame, send to backend, and advance pipeline
  const captureNow = useCallback(async () => {
    const video = videoRef.current;
    if (!video || video.readyState < 2) return;

    setPipelineStatus({ stage: "detected", count: 1 });

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
    const base64 = dataUrl.split(",")[1];

    const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

    // Show "identifying" immediately since we know we're sending a face
    setPipelineStatus({ stage: "identifying", trackId: -1 });

    try {
      const res = await fetch(`${backendUrl}/api/capture/frame`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frame: base64, timestamp: Date.now(), source: "voice_command", target: true }),
      });
      if (res.ok) {
        const data = await res.json();
        setDetectionCount(data.detections?.length ?? 0);
        // If we got identifications back in this response, process them
        if (data.identifications) {
          for (const ident of data.identifications) {
            if (ident.status === "identified" && ident.name && !identifiedRef.current.has(ident.name)) {
              identifiedRef.current.add(ident.name);
              setPipelineStatus({ stage: "identified", name: ident.name });
              setTimeout(() => {
                setPipelineStatus({ stage: "researching", name: ident.name! });
                prevSourceCountRef.current = 0;
                startStream(ident.name!);
              }, 1200);
              return;
            }
          }
        }
        // If no instant identification, pipeline is in progress —
        // the regular useFrameCapture polling will pick up when identification completes
      }
    } catch {
      // Fall back to scanning
      setPipelineStatus({ stage: "scanning" });
    }
  }, [videoRef, startStream, isStreaming]);

  const voiceCommands = useCallback(() => [
    {
      trigger: "target",
      action: () => {
        if (camStatus === "live") captureNow();
      },
    },
    {
      trigger: "lock on",
      action: () => {
        if (camStatus === "live") captureNow();
      },
    },
    {
      trigger: "scan",
      action: () => {
        if (camStatus === "live") captureNow();
      },
    },
  ], [camStatus, captureNow]);

  const { status: voiceStatus, lastCommand: voiceLastCommand } = useVoiceCommands({
    commands: voiceCommands(),
    enabled: voiceEnabled,
    onTranscript: setLastTranscript,
  });

  const drag = useRef({ sx: 0, sy: 0, dx: 0, dy: 0, moved: false, id: null as string | null });
  const vscRef = useRef(1);

  // TopBar height (h-12 = 48px) + StatusBar height (h-8 = 32px) = 80px
  useEffect(() => {
    const fn = () => {
      const availW = window.innerWidth - SIDE_W - 40;
      const s = Math.min(availW / BW, (window.innerHeight - 80) / BH, 1);
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
        const cx = Math.max(0, Math.min(BW - BDW, d.dx + mx));
        const cy = Math.max(0, Math.min(BH - BDH, d.dy + my));
        const clamped = clampOutOfCamZone(cx, cy, BDW, BDH);
        setBoardData(prev => ({ ...prev, blu: clamped }));
      } else {
        setBoardData(prev => ({
          ...prev, srcs: prev.srcs.map(s => {
            if (s.id !== d.id) return s;
            const cx = Math.max(0, Math.min(BW - GW, d.dx + mx));
            const cy = Math.max(0, Math.min(BH - GH, d.dy + my));
            const clamped = clampOutOfCamZone(cx, cy, GW, GH);
            return { ...s, x: clamped.x, y: clamped.y };
          }),
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
   */
  const selectPerson = useCallback((p: IntelPerson) => {
    if (activePerson?.id === p.id) return;
    setBoardFade(false);
    setTimeout(() => {
      setActivePerson(p);
      const data = buildBoardData(p);
      setBoardData(data);
      setBoardFade(true);
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
      fontFamily: "'Inter',system-ui,sans-serif", display: "flex", flexDirection: "column",
      background: "var(--bg-dark)",
    }}>
      <style>{`
        @keyframes sh{0%{background-position:-150px 0}100%{background-position:150px 0}}
        @keyframes fi{0%{opacity:0;transform:scale(.78)}100%{opacity:1;transform:scale(1)}}
        @keyframes sm{0%{transform:translateY(-100%)}100%{transform:translateY(100%)}}
        @keyframes pf{0%{transform:translateY(0);opacity:0}15%{opacity:.3}85%{opacity:.3}100%{transform:translateY(-140px);opacity:0}}
        @keyframes mi{0%{opacity:0;transform:scale(.93) translateY(12px)}100%{opacity:1;transform:scale(1) translateY(0)}}
        @keyframes dl{0%{stroke-dashoffset:600}100%{stroke-dashoffset:0}}
        @keyframes camPulse{0%,100%{opacity:1;box-shadow:0 0 6px rgba(74,222,128,.6)}50%{opacity:.55;box-shadow:0 0 3px rgba(74,222,128,.3)}}
        @keyframes staticFlicker{0%{background-position:0 0}33%{background-position:50px 30px}66%{background-position:20px 60px}100%{background-position:70px 10px}}
        @keyframes scanPulse{0%,100%{opacity:1}50%{opacity:.4}}
        @keyframes listSlideIn{0%{opacity:0;transform:translateY(-8px)}100%{opacity:1;transform:translateY(0)}}
        @keyframes radarSpin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
        @keyframes faceScanLine{0%{transform:translateY(-16px);opacity:0}20%{opacity:1}80%{opacity:1}100%{transform:translateY(16px);opacity:0}}
        @keyframes checkCircle{0%{stroke-dasharray:0 150}100%{stroke-dasharray:150 0}}
        @keyframes checkMark{0%{stroke-dashoffset:40}100%{stroke-dashoffset:0}}
      `}</style>

      {/* TOP BAR */}
      <TopBar />

      {/* MAIN CONTENT ROW */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* LEFT SIDEBAR */}
        <Sidebar
          people={people}
          activePerson={activePerson}
          onSelect={selectPerson}
          search={search}
          setSearch={setSearch}
          onSearchSubmit={handleSearchSubmit}
          isStreaming={isStreaming}
        />

        {/* BOARD AREA — fills entire right space with green background */}
        <div style={{
          flex: 1, position: "relative", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden",
          backgroundColor: "var(--board-bg)",
          backgroundImage: [
            "linear-gradient(rgba(120,180,80,.03) 1px, transparent 1px)",
            "linear-gradient(90deg, rgba(120,180,80,.03) 1px, transparent 1px)",
          ].join(", "),
          backgroundSize: "40px 40px, 40px 40px",
        }}>
          {/* Vignette overlay */}
          <div style={{
            position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1,
            background: "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,.35) 100%)",
          }} />

          {/* PIPELINE STATUS OVERLAY — replaces idle placeholder with live feedback */}
          {!activePerson && (
            <div style={{
              position: "absolute", top: "50%", left: "50%",
              transform: "translate(-50%, -50%)",
              textAlign: "center", pointerEvents: "none", userSelect: "none",
              zIndex: 2,
              display: "flex", flexDirection: "column", alignItems: "center", gap: 18,
            }}>
              {/* Dynamic icon based on pipeline stage */}
              {pipelineStatus.stage === "idle" && (
                <svg width="52" height="52" viewBox="0 0 52 52" style={{ opacity: 0.18 }}>
                  <circle cx="26" cy="26" r="22" fill="none" stroke="rgba(120,180,80,1)" strokeWidth="1" />
                  <circle cx="26" cy="26" r="13" fill="none" stroke="rgba(120,180,80,1)" strokeWidth="0.5" />
                  <line x1="2"  y1="26" x2="12" y2="26" stroke="rgba(120,180,80,1)" strokeWidth="1" />
                  <line x1="40" y1="26" x2="50" y2="26" stroke="rgba(120,180,80,1)" strokeWidth="1" />
                  <line x1="26" y1="2"  x2="26" y2="12" stroke="rgba(120,180,80,1)" strokeWidth="1" />
                  <line x1="26" y1="40" x2="26" y2="50" stroke="rgba(120,180,80,1)" strokeWidth="1" />
                </svg>
              )}

              {pipelineStatus.stage === "scanning" && (
                <div style={{ position: "relative", width: 64, height: 64 }}>
                  {/* Radar sweep */}
                  <svg width="64" height="64" viewBox="0 0 64 64" style={{ animation: "radarSpin 3s linear infinite" }}>
                    <circle cx="32" cy="32" r="28" fill="none" stroke="rgba(120,180,80,.15)" strokeWidth="1" />
                    <circle cx="32" cy="32" r="18" fill="none" stroke="rgba(120,180,80,.1)" strokeWidth="0.5" />
                    <circle cx="32" cy="32" r="8" fill="none" stroke="rgba(120,180,80,.08)" strokeWidth="0.5" />
                    <line x1="32" y1="32" x2="32" y2="4" stroke="rgba(120,180,80,.4)" strokeWidth="1.5" />
                    <path d="M32 32 L32 4 A28 28 0 0 1 56 20 Z" fill="rgba(120,180,80,.06)" />
                  </svg>
                </div>
              )}

              {(pipelineStatus.stage === "detected" || pipelineStatus.stage === "identifying") && (
                <div style={{ position: "relative", width: 64, height: 64 }}>
                  {/* Face scan animation */}
                  <svg width="64" height="64" viewBox="0 0 64 64">
                    {/* Face outline brackets */}
                    <path d="M12 20 L12 12 L20 12" fill="none" stroke="rgba(120,180,80,.6)" strokeWidth="2" />
                    <path d="M44 12 L52 12 L52 20" fill="none" stroke="rgba(120,180,80,.6)" strokeWidth="2" />
                    <path d="M52 44 L52 52 L44 52" fill="none" stroke="rgba(120,180,80,.6)" strokeWidth="2" />
                    <path d="M20 52 L12 52 L12 44" fill="none" stroke="rgba(120,180,80,.6)" strokeWidth="2" />
                    {/* Scan line */}
                    <line x1="14" y1="32" x2="50" y2="32" stroke="rgba(120,180,80,.4)" strokeWidth="1"
                      style={{ animation: "faceScanLine 2s ease-in-out infinite" }} />
                  </svg>
                </div>
              )}

              {pipelineStatus.stage === "identified" && (
                <div style={{ position: "relative", width: 64, height: 64, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {/* Checkmark circle */}
                  <svg width="52" height="52" viewBox="0 0 52 52">
                    <circle cx="26" cy="26" r="22" fill="none" stroke="rgba(74,222,128,.5)" strokeWidth="2"
                      style={{ animation: "checkCircle .6s ease-out forwards" }} />
                    <path d="M16 26 L22 32 L36 18" fill="none" stroke="rgba(74,222,128,.8)" strokeWidth="2.5"
                      strokeLinecap="round" strokeLinejoin="round"
                      strokeDasharray="40" style={{ animation: "checkMark .4s ease-out .3s forwards", strokeDashoffset: 40 }} />
                  </svg>
                </div>
              )}

              {pipelineStatus.stage === "researching" && (
                <div style={{ position: "relative", width: 64, height: 64, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {/* Spinning loader */}
                  <svg width="52" height="52" viewBox="0 0 52 52" style={{ animation: "radarSpin 1.5s linear infinite" }}>
                    <circle cx="26" cy="26" r="22" fill="none" stroke="rgba(120,180,80,.1)" strokeWidth="2" />
                    <path d="M26 4 A22 22 0 0 1 48 26" fill="none" stroke="rgba(120,180,80,.5)" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </div>
              )}

              {/* Status text */}
              <div style={{
                fontFamily: "var(--font-heading)", fontSize: 22,
                letterSpacing: "0.3em",
                color: pipelineStatus.stage === "identified" ? "rgba(74,222,128,.5)" :
                       pipelineStatus.stage === "idle" ? "rgba(120,180,80,.22)" : "rgba(120,180,80,.4)",
                transition: "color .3s",
              }}>
                {pipelineStatus.stage === "idle" && "NO ACTIVE TARGET"}
                {pipelineStatus.stage === "scanning" && "SCANNING"}
                {pipelineStatus.stage === "detected" && "FACE DETECTED"}
                {pipelineStatus.stage === "identifying" && "IDENTIFYING"}
                {pipelineStatus.stage === "identified" && `${pipelineStatus.name.toUpperCase()}`}
                {pipelineStatus.stage === "researching" && `RESEARCHING`}
              </div>

              {/* Sub-status text */}
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 10.5,
                letterSpacing: ".07em",
                color: pipelineStatus.stage === "idle" ? "rgba(120,180,80,.13)" : "rgba(120,180,80,.3)",
                lineHeight: 2, textTransform: "uppercase",
                transition: "color .3s",
              }}>
                {pipelineStatus.stage === "idle" && (
                  <>SELECT A SUBJECT FROM THE SIDEBAR TO BEGIN ANALYSIS<br />OR CONNECT THE GLASSES CAMERA TO SCAN A NEW TARGET</>
                )}
                {pipelineStatus.stage === "scanning" && "LOOKING FOR FACES IN CAMERA FEED..."}
                {pipelineStatus.stage === "detected" && "NEW PERSON DETECTED — CAPTURING FACE..."}
                {pipelineStatus.stage === "identifying" && (
                  <>RUNNING FACIAL RECOGNITION...<br />
                  <span style={{ fontSize: 9, opacity: .7 }}>PIMEYES REVERSE IMAGE SEARCH IN PROGRESS</span></>
                )}
                {pipelineStatus.stage === "identified" && "MATCH FOUND — INITIATING RESEARCH..."}
                {pipelineStatus.stage === "researching" && (
                  <>DEPLOYING BROWSER AGENTS ON {pipelineStatus.name.toUpperCase()}<br />
                  <span style={{ fontSize: 9, opacity: .7 }}>RESULTS WILL APPEAR ON THE BOARD SHORTLY</span></>
                )}
              </div>

              {/* Progress dots for active stages */}
              {pipelineStatus.stage !== "idle" && (
                <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                  {["detected", "identifying", "identified", "researching"].map((step, i) => {
                    const stages = ["scanning", "detected", "identifying", "identified", "researching"];
                    const currentIdx = stages.indexOf(pipelineStatus.stage);
                    const stepIdx = i + 1; // offset since scanning is step 0
                    const isComplete = currentIdx > stepIdx;
                    const isActive = currentIdx === stepIdx;
                    return (
                      <div key={step} style={{
                        width: 6, height: 6, borderRadius: "50%",
                        background: isComplete ? "rgba(74,222,128,.5)" :
                                   isActive ? "rgba(120,180,80,.6)" : "rgba(120,180,80,.12)",
                        boxShadow: isActive ? "0 0 8px rgba(120,180,80,.3)" : "none",
                        animation: isActive ? "scanPulse 1.5s ease-in-out infinite" : "none",
                        transition: "background .3s",
                      }} />
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* CAMERA FEED — fixed top-right of board area */}
          <div style={{ position: "absolute", top: 0, right: 0, bottom: 0, left: 0, pointerEvents: "none", zIndex: 20 }}>
            <CameraFeed
              videoRef={videoRef}
              status={camStatus}
              onConnect={camConnect}
              onWebcam={camWebcam}
              onDisconnect={camDisconnect}
              error={camError}
              detectionCount={detectionCount}
            />

            {/* Voice command controls — below camera feed */}
            {camStatus === "live" && (
              <div style={{
                position: "absolute", top: CAM_H + CAM_PAD + 8, right: CAM_PAD,
                display: "flex", gap: 8, alignItems: "center",
                pointerEvents: "auto",
              }}>
                {/* Mic toggle */}
                <button
                  onClick={() => setVoiceEnabled(v => !v)}
                  style={{
                    padding: "5px 12px", borderRadius: 3,
                    background: voiceEnabled ? "rgba(74,124,63,.4)" : "rgba(0,0,0,.5)",
                    border: `1px solid ${voiceEnabled ? "rgba(120,180,80,.4)" : "rgba(120,180,80,.15)"}`,
                    color: voiceEnabled ? "rgba(120,180,80,.9)" : "rgba(120,180,80,.5)",
                    fontSize: 11, fontFamily: "monospace", letterSpacing: ".1em",
                    cursor: "pointer", transition: "all .15s",
                    display: "flex", alignItems: "center", gap: 6,
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/>
                    <path d="M19 10v2a7 7 0 01-14 0v-2"/>
                    <line x1="12" y1="19" x2="12" y2="23"/>
                  </svg>
                  {voiceEnabled ? "VOICE ON" : "VOICE"}
                </button>

                {/* Manual target button — triggers face identification */}
                <button
                  onClick={captureNow}
                  disabled={isStreaming}
                  style={{
                    padding: "5px 12px", borderRadius: 3,
                    background: isStreaming ? "rgba(0,0,0,.3)" : "rgba(239,68,68,.15)",
                    border: `1px solid ${isStreaming ? "rgba(120,180,80,.1)" : "rgba(239,68,68,.4)"}`,
                    color: isStreaming ? "rgba(120,180,80,.3)" : "rgba(239,68,68,.9)",
                    fontSize: 11, fontFamily: "monospace", letterSpacing: ".15em",
                    fontWeight: 700,
                    cursor: isStreaming ? "not-allowed" : "pointer",
                    transition: "all .15s",
                  }}
                >
                  TARGET
                </button>

                {/* Voice status indicator */}
                {voiceEnabled && (
                  <div style={{
                    fontSize: 9, fontFamily: "monospace", letterSpacing: ".08em",
                    color: voiceStatus === "listening" ? "rgba(120,180,80,.6)" :
                           voiceStatus === "processing" ? "rgba(74,222,128,.8)" :
                           "rgba(239,68,68,.5)",
                    animation: voiceStatus === "listening" ? "scanPulse 2s ease-in-out infinite" : "none",
                  }}>
                    {voiceStatus === "listening" && "LISTENING..."}
                    {voiceStatus === "processing" && `CMD: ${voiceLastCommand?.toUpperCase()}`}
                    {voiceStatus === "error" && "MIC ERROR"}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* CAMERA WRAPPER — scaled board canvas */}
          <div style={{
            width: BW, height: BH, position: "relative", zIndex: 5,
            transform: cam, transformOrigin: "center center",
            transition: tier === 3 ? "transform 0.85s cubic-bezier(.25,.46,.45,.94)" : "transform 1s cubic-bezier(.25,.46,.45,.94)",
          }}>
            {/* BOARD CONTENT — Crossfade wrapper */}
            <div style={{
              position: "absolute", top: 0, left: 0, width: BW, height: BH, zIndex: 10,
              opacity: boardFade ? 1 : 0, transition: "opacity .4s ease",
            }}>
              {/* SVG strings */}
              <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 8 }}>
                {blu && srcs.map(s => (
                  <g key={s.id}>
                    <path d={catenary(s.x + GW / 2, s.y + 4, bpx, bpy)} fill="none" stroke="rgba(140,20,20,.08)" strokeWidth={5} />
                    <path d={catenary(s.x + GW / 2, s.y + 4, bpx, bpy)} fill="none" stroke="#c0392b" strokeWidth={1.5} opacity={.6}
                      strokeDasharray="600" style={{ animation: "dl 1.5s ease-out forwards" }} />
                  </g>
                ))}
              </svg>

              {/* SUMMARY DOC — PersonCard-style */}
              {blu && activePerson && (
                <div
                  onMouseDown={e => startDrag(e, "blue", blu.x, blu.y)}
                  onClick={() => clickDoc({ kind: "summary" })}
                  style={{
                    position: "absolute", left: blu.x, top: blu.y, width: BDW, height: BDH,
                    background: PAPERS[1].bg, border: `1px solid ${PAPERS[1].bd}`, borderRadius: 3,
                    padding: "10px 12px 12px",
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

                  {/* Gold pushpin */}
                  <div style={{
                    position: "absolute", top: -8, left: "50%", transform: "translateX(-50%)",
                    width: 16, height: 16, borderRadius: "50%",
                    background: "radial-gradient(circle at 40% 35%, #e8c040, #d4a017, #b8860b)",
                    border: "2px solid #8a6000",
                    boxShadow: "0 2px 5px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.2)",
                    zIndex: 10,
                  }} />

                  {/* Status badge */}
                  <div style={{
                    position: "absolute", top: 8, right: 8,
                    fontSize: 8, padding: "2px 5px", borderRadius: 2,
                    background: "#3498db", color: "#fff",
                    fontFamily: "var(--font-mono)", fontWeight: 700, letterSpacing: ".08em",
                    zIndex: 5,
                  }}>
                    {srcs.length} SOURCE{srcs.length !== 1 ? "S" : ""}
                  </div>

                  {/* Profile photo area */}
                  <div style={{
                    width: 56, height: 70, margin: "10px auto 8px",
                    background: "linear-gradient(135deg,#d8dde5,#c4cad4)",
                    border: "2px solid #a8adb8",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    position: "relative", zIndex: 1,
                  }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="8" r="4" fill="#8090a0" />
                      <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" fill="#8090a0" />
                    </svg>
                  </div>

                  {/* Name in Bebas Neue */}
                  <div style={{
                    textAlign: "center", fontFamily: "var(--font-heading)", fontSize: 18,
                    letterSpacing: 2, color: "#1a1a2e", position: "relative", zIndex: 1,
                    lineHeight: 1.1, marginBottom: 4,
                  }}>
                    {activePerson.summary.nm.toUpperCase()}
                  </div>

                  {/* Job / Location metadata */}
                  {(activePerson.summary.title || activePerson.summary.location) && (
                    <div style={{ position: "relative", zIndex: 1, marginBottom: 5 }}>
                      {activePerson.summary.title && (
                        <div style={{ display: "flex", alignItems: "center", gap: 4, justifyContent: "center", marginBottom: 2 }}>
                          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#6b7a58" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/>
                          </svg>
                          <span style={{ color: "#5a6a48", fontSize: 8, fontFamily: "var(--font-mono)" }}>
                            {activePerson.summary.title}
                          </span>
                        </div>
                      )}
                      {activePerson.summary.location && (
                        <div style={{ display: "flex", alignItems: "center", gap: 4, justifyContent: "center" }}>
                          <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#6b7a58" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/>
                          </svg>
                          <span style={{ color: "#5a6a48", fontSize: 8, fontFamily: "var(--font-mono)" }}>
                            {activePerson.summary.location}
                          </span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Summary snippet */}
                  <div style={{
                    color: "#4b5563", fontSize: 8.5, lineHeight: 1.45,
                    overflow: "hidden", position: "relative", zIndex: 1,
                    display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
                    textAlign: "center",
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
                    onClick={() => !s.loading && clickDoc({
                      kind: "source", id: s.id, nm: s.nm, tp: s.tp, sn: s.sn,
                      sessionId: s.sessionId, liveUrl: s.liveUrl, shareUrl: s.shareUrl, sessionStatus: s.sessionStatus,
                    })}
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
                        {s.sessionStatus === "running" && (
                          <div style={{
                            position: "absolute", top: -8, right: -5, width: 7, height: 7,
                            borderRadius: "50%", background: "#4ade80",
                            animation: "camPulse 2s ease-in-out infinite", zIndex: 5,
                          }} />
                        )}
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

        </div>
      </div>

      {/* BOTTOM STATUS BAR */}
      <StatusBar people={people} activePerson={activePerson} />

      {/* INTELLIGENCE MODAL */}
      {modalVis && selDoc && (
        <div onClick={backFromDoc} style={{
          position: "fixed", inset: 0, zIndex: 100,
          background: "rgba(0,0,0,.65)", backdropFilter: "blur(6px)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            position: "relative",
            width: selDoc.sessionId ? 760 : selDoc.kind === "summary" ? 580 : 520,
            maxHeight: selDoc.sessionId ? "90vh" : "85vh",
            overflowY: "auto",
            background: "#0e0e11",
            border: "1px solid rgba(255,255,255,.08)",
            borderRadius: 2, padding: "24px 28px 28px",
            boxShadow: "0 24px 64px rgba(0,0,0,.8), inset 0 1px 0 rgba(255,255,255,.04)",
            animation: "mi .3s ease-out",
          }}>
            {/* Grain overlay */}
            <div style={{
              position: "absolute", inset: 0, borderRadius: 2, pointerEvents: "none", opacity: .04, zIndex: 0,
              backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
              backgroundSize: "200px 200px",
            }} />

            {/* Header row */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20, position: "relative", zIndex: 1 }}>
              <span style={{ color: "#52525b", fontSize: 9, fontWeight: 600, letterSpacing: ".18em", fontFamily: "monospace" }}>
                {selDoc.kind === "summary" ? "INTELLIGENCE SUMMARY" : selDoc.tp}
              </span>
              <button onClick={backFromDoc} style={{
                background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.07)",
                borderRadius: 2, color: "#52525b",
                width: 26, height: 26, cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11,
              }}>✕</button>
            </div>

            {selDoc.kind === "summary" && activePerson ? (
              <DossierModal person={activePerson} />
            ) : selDoc.sessionId ? (
              <div style={{ position: "relative", zIndex: 1 }}>
                <BrowserSessionViewer
                  sessionId={selDoc.sessionId}
                  sessionStatus={selDoc.sessionStatus ?? "pending"}
                  liveUrl={selDoc.liveUrl}
                  shareUrl={selDoc.shareUrl}
                  sourceNm={selDoc.nm ?? ""}
                  sourceTp={selDoc.tp ?? ""}
                />
              </div>
            ) : (
              <div style={{ position: "relative", zIndex: 1 }}>
                <div style={{ color: "#f4f4f5", fontSize: 16, fontWeight: 600, letterSpacing: ".02em", marginBottom: 14 }}>{selDoc.nm}</div>
                <div style={{ height: 1, background: "rgba(255,255,255,.07)", marginBottom: 14 }} />
                <div style={{ color: "#a1a1aa", fontSize: 13, lineHeight: 1.75 }}>{selDoc.sn}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
