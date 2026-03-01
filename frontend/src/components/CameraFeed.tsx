"use client";

import { useState } from "react";

import type { StreamStatus } from "@/lib/useGlassesStream";

const CAM_W = 380;
const CAM_H = 240;
const CAM_PAD = 16;

interface CameraFeedProps {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  status: StreamStatus;
  onConnect: (roomCode: string) => void;
  onWebcam?: () => void;
  onDisconnect: () => void;
  error: string | null;
  detectionCount?: number;
}

function RoomCodeInput({ onSubmit }: { onSubmit: (code: string) => void }) {
  const [code, setCode] = useState("");
  const [hovered, setHovered] = useState(false);
  const enabled = code.length >= 1;
  return (
    <div style={{
      position: "absolute", bottom: 10, left: 12, right: 12,
      display: "flex", gap: 6,
    }}>
      <input
        value={code}
        onChange={e => setCode(e.target.value.toUpperCase().slice(0, 12))}
        placeholder="ROOM CODE"
        maxLength={12}
        style={{
          flex: 1, padding: "5px 10px",
          background: "rgba(0,0,0,.5)", border: "1px solid rgba(120,180,80,.2)",
          borderRadius: 3, color: "rgba(120,180,80,.7)",
          fontSize: 13, fontFamily: "monospace", letterSpacing: ".15em",
          outline: "none", textTransform: "uppercase",
        }}
        onKeyDown={e => { if (e.key === "Enter" && enabled) onSubmit(code); }}
      />
      <button
        onClick={() => enabled && onSubmit(code)}
        disabled={!enabled}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{
          padding: "5px 12px",
          background: enabled
            ? hovered ? "rgba(74,124,63,.6)" : "rgba(74,124,63,.4)"
            : "rgba(0,0,0,.3)",
          border: `1px solid ${enabled && hovered ? "rgba(120,180,80,.4)" : "rgba(120,180,80,.2)"}`,
          borderRadius: 3,
          color: enabled
            ? hovered ? "rgba(120,180,80,.85)" : "rgba(120,180,80,.6)"
            : "rgba(120,180,80,.6)",
          fontSize: 12, fontFamily: "monospace", letterSpacing: ".1em",
          cursor: enabled ? "pointer" : "not-allowed",
          transition: "background .15s, border-color .15s, color .15s",
          boxShadow: enabled && hovered ? "0 0 8px rgba(120,180,80,.15)" : "none",
        }}
      >
        LINK
      </button>
    </div>
  );
}

export function CameraFeed({ videoRef, status, onConnect, onWebcam, onDisconnect, error, detectionCount }: CameraFeedProps) {
  const isLive = status === "live";
  const isConnecting = status === "connecting";
  const isError = status === "error";

  return (
    <div style={{
      position: "absolute", top: CAM_PAD, right: CAM_PAD,
      width: CAM_W, height: CAM_H, zIndex: 18,
      border: "1px solid rgba(120,180,80,.15)",
      borderRadius: 4, overflow: "hidden",
      background: isLive ? "#0a0a0a" : "#0d1108",
      boxShadow: "0 2px 12px rgba(0,0,0,.4)",
      pointerEvents: "auto",
    }}>
      {/* Video element — always in DOM so ref is valid when ontrack fires */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{
          position: "absolute", inset: 0,
          width: "100%", height: "100%", objectFit: "cover",
          display: isLive ? "block" : "none",
        }}
      />

      {/* Disconnected placeholder */}
      {status === "disconnected" && (
        <>
          {/* Static noise */}
          <div style={{
            position: "absolute", inset: 0, opacity: .06,
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='100' height='100' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='0.85' numOctaves='4' seed='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
            backgroundSize: "100px 100px", animation: "staticFlicker 0.15s steps(3) infinite",
          }} />
          {/* Scan lines */}
          <div style={{
            position: "absolute", inset: 0, opacity: .04,
            background: "repeating-linear-gradient(0deg,transparent 0px,transparent 2px,rgba(255,255,255,.15) 2px,rgba(255,255,255,.15) 3px)",
          }} />
          {/* No-signal icon */}
          <div style={{ position: "absolute", top: "38%", left: "50%", transform: "translate(-50%,-50%)" }}>
            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#3a5030" strokeWidth="1.5" strokeLinecap="round">
              <path d="M16.3 5H4.7A1.7 1.7 0 003 6.7v10.6A1.7 1.7 0 004.7 19h11.6a1.7 1.7 0 001.7-1.7V6.7A1.7 1.7 0 0016.3 5z" />
              <path d="M21 8l-3 2v4l3 2V8z" />
              <line x1="2" y1="2" x2="22" y2="22" stroke="#4a4030" />
            </svg>
          </div>
          {/* Room code input + webcam fallback */}
          <RoomCodeInput onSubmit={onConnect} />
          {onWebcam && (
            <button
              onClick={onWebcam}
              style={{
                position: "absolute", top: 8, right: 8,
                padding: "4px 10px", borderRadius: 3,
                background: "rgba(74,124,63,.3)",
                border: "1px solid rgba(120,180,80,.25)",
                color: "rgba(120,180,80,.7)",
                fontSize: 10, fontFamily: "monospace", letterSpacing: ".1em",
                cursor: "pointer",
              }}
            >
              WEBCAM
            </button>
          )}
        </>
      )}

      {/* Connecting state */}
      {isConnecting && (
        <>
          <div style={{
            position: "absolute", inset: 0, opacity: .04,
            background: "repeating-linear-gradient(0deg,transparent 0px,transparent 2px,rgba(255,255,255,.15) 2px,rgba(255,255,255,.15) 3px)",
          }} />
          <div style={{
            position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)",
            textAlign: "center",
          }}>
            <div style={{
              fontSize: 14, fontFamily: "monospace", color: "rgba(120,180,80,.5)",
              letterSpacing: ".15em", animation: "scanPulse 1.5s ease-in-out infinite",
            }}>
              CONNECTING...
            </div>
          </div>
        </>
      )}

      {/* Error state */}
      {isError && (
        <>
          <div style={{
            position: "absolute", inset: 0, opacity: .03,
            background: "repeating-linear-gradient(0deg,transparent 0px,transparent 2px,rgba(255,80,80,.2) 2px,rgba(255,80,80,.2) 3px)",
          }} />
          <div style={{
            position: "absolute", top: "35%", left: "50%", transform: "translate(-50%,-50%)",
            textAlign: "center", width: "85%",
          }}>
            <div style={{
              fontSize: 12, fontFamily: "monospace", color: "rgba(239,68,68,.6)",
              letterSpacing: ".1em", lineHeight: 1.4,
            }}>
              {error || "CONNECTION FAILED"}
            </div>
          </div>
          {/* Retry with room code input */}
          <RoomCodeInput onSubmit={onConnect} />
        </>
      )}

      {/* Screen glare — always present */}
      <div style={{
        position: "absolute", inset: 0, pointerEvents: "none",
        background: "linear-gradient(145deg,rgba(255,255,255,.02) 0%,transparent 40%,transparent 60%,rgba(255,255,255,.01) 100%)",
      }} />

      {/* Detection count badge */}
      {isLive && detectionCount !== undefined && detectionCount > 0 && (
        <div style={{
          position: "absolute", top: 12, left: 12,
          padding: "3px 9px", borderRadius: 3,
          background: "rgba(0,0,0,.6)", border: "1px solid rgba(120,180,80,.25)",
          fontSize: 12, fontFamily: "monospace", color: "rgba(120,180,80,.8)",
          letterSpacing: ".08em",
        }}>
          {detectionCount} DETECTED
        </div>
      )}

      {/* Disconnect button when live */}
      {isLive && (
        <button
          onClick={onDisconnect}
          style={{
            position: "absolute", bottom: 10, right: 10,
            padding: "3px 9px", borderRadius: 3,
            background: "rgba(0,0,0,.5)", border: "1px solid rgba(239,68,68,.3)",
            fontSize: 11, fontFamily: "monospace", color: "rgba(239,68,68,.6)",
            letterSpacing: ".1em", cursor: "pointer",
          }}
        >
          DISCONNECT
        </button>
      )}

      {/* Status dot */}
      <div style={{
        position: "absolute", top: 12, right: 12, width: 10, height: 10, borderRadius: "50%",
        background: isLive
          ? "radial-gradient(circle,#4ade80,#22c55e)"
          : isConnecting
            ? "radial-gradient(circle,#fbbf24,#f59e0b)"
            : "radial-gradient(circle,#ef4444,#dc2626)",
        boxShadow: isLive
          ? "0 0 6px rgba(74,222,128,.6),0 0 12px rgba(74,222,128,.2)"
          : isConnecting
            ? "0 0 6px rgba(251,191,36,.5)"
            : "0 0 4px rgba(239,68,68,.4)",
        animation: isLive ? "camPulse 2s ease-in-out infinite" : isConnecting ? "scanPulse 1.5s ease-in-out infinite" : "none",
      }} />
    </div>
  );
}
