"use client";

const FR = 14;
const CAM_W = 240;
const CAM_H = 150;
const CAM_PAD = 16;

interface CameraFeedProps {
  connected: boolean;
}

export function CameraFeed({ connected }: CameraFeedProps) {
  return (
    <div style={{ position: "absolute", top: FR + CAM_PAD, right: FR + CAM_PAD, width: CAM_W, height: CAM_H, zIndex: 18 }}>
      {/* Monitor bezel frame */}
      <div style={{
        position: "absolute", inset: -6,
        background: "linear-gradient(145deg,#1e2838,#151c28,#1a2232)", borderRadius: 10,
        border: "1px solid #2a3448", boxShadow: "0 4px 20px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.04)",
      }}>
        {/* Corner screws */}
        {[{ top: 4, left: 4 }, { top: 4, right: 4 }, { bottom: 4, left: 4 }, { bottom: 4, right: 4 }].map((p, i) => (
          <div key={i} style={{
            position: "absolute", width: 7, height: 7, borderRadius: "50%", ...p,
            background: "radial-gradient(circle at 40% 35%,#5a6270,#3a4250)",
            border: "1px solid #4a5260", boxShadow: "inset 0 1px 1px rgba(255,255,255,.08)",
          }} />
        ))}
      </div>
      {/*
       * CAMERA FEED SCREEN — Replace inner content with:
       * <video> element for Meta glasses live stream, or
       * <canvas> for OpenCV object detection overlay
       */}
      <div style={{
        position: "absolute", inset: 0, borderRadius: 6, overflow: "hidden",
        background: connected ? "#0a0a0a" : "#111418", border: "1px solid #0a0e14",
      }}>
        {!connected && (
          <>
            <div style={{
              position: "absolute", inset: 0, opacity: .08,
              backgroundImage: `url("data:image/svg+xml,%3Csvg width='100' height='100' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='0.85' numOctaves='4' seed='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
              backgroundSize: "100px 100px", animation: "staticFlicker 0.15s steps(3) infinite",
            }} />
            <div style={{
              position: "absolute", inset: 0, opacity: .04,
              background: "repeating-linear-gradient(0deg,transparent 0px,transparent 2px,rgba(255,255,255,.15) 2px,rgba(255,255,255,.15) 3px)",
            }} />
            <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)" }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#3a4050" strokeWidth="1.5" strokeLinecap="round">
                <path d="M16.3 5H4.7A1.7 1.7 0 003 6.7v10.6A1.7 1.7 0 004.7 19h11.6a1.7 1.7 0 001.7-1.7V6.7A1.7 1.7 0 0016.3 5z" />
                <path d="M21 8l-3 2v4l3 2V8z" />
                <line x1="2" y1="2" x2="22" y2="22" stroke="#4a3035" />
              </svg>
            </div>
          </>
        )}
        <div style={{
          position: "absolute", inset: 0, pointerEvents: "none",
          background: "linear-gradient(145deg,rgba(255,255,255,.02) 0%,transparent 40%,transparent 60%,rgba(255,255,255,.01) 100%)",
        }} />
        {/* Status dot */}
        <div style={{
          position: "absolute", top: 8, right: 8, width: 8, height: 8, borderRadius: "50%",
          background: connected ? "radial-gradient(circle,#4ade80,#22c55e)" : "radial-gradient(circle,#ef4444,#dc2626)",
          boxShadow: connected ? "0 0 6px rgba(74,222,128,.6),0 0 12px rgba(74,222,128,.2)" : "0 0 4px rgba(239,68,68,.4)",
          animation: connected ? "camPulse 2s ease-in-out infinite" : "none",
        }} />
      </div>
    </div>
  );
}
