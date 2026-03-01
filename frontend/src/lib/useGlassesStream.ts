// RESEARCH: VisionClaw (1.4k stars, Feb 2026) provides signaling server
// DECISION: Using VisionClaw's WebSocket signaling protocol directly
// FIX: Matched working viewer at visionclaw-signal.fly.dev — PC created in
//      offer handler, STUN+TURN ice servers, srcObject set on ICE connected
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type StreamStatus = "disconnected" | "connecting" | "live" | "error";

interface UseGlassesStreamReturn {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  status: StreamStatus;
  connect: (roomCode: string) => void;
  disconnect: () => void;
  error: string | null;
}

const SIGNAL_WS = "wss://visionclaw-signal.fly.dev";
const TURN_ENDPOINT = "https://visionclaw-signal.fly.dev/api/turn";

const STUN_SERVERS: RTCIceServer[] = [
  { urls: "stun:stun.l.google.com:19302" },
  { urls: "stun:stun1.l.google.com:19302" },
];

export function useGlassesStream(): UseGlassesStreamReturn {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [status, setStatus] = useState<StreamStatus>("disconnected");
  const [error, setError] = useState<string | null>(null);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    pcRef.current?.close();
    pcRef.current = null;
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setStatus("disconnected");
    setError(null);
  }, []);

  const connect = useCallback(
    (roomCode: string) => {
      const trimmed = roomCode.trim();
      if (!trimmed || !/^[a-zA-Z0-9]+$/.test(trimmed)) {
        setError("Invalid room code");
        setStatus("error");
        return;
      }

      disconnect();
      setStatus("connecting");
      setError(null);

      const pendingCandidates: RTCIceCandidateInit[] = [];

      // Step 1: Connect to signaling server — PC is NOT created yet
      const ws = new WebSocket(SIGNAL_WS);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("[WebRTC] Signaling connected, joining room:", trimmed);
        ws.send(JSON.stringify({ type: "join", room: trimmed }));
      };

      ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        console.log(
          "[WebRTC] ←",
          msg.type,
          msg.type === "candidate" ? "(ICE)" : JSON.stringify(msg)
        );

        if (msg.type === "error") {
          console.error("[WebRTC] Server error:", msg);
          setError(msg.message || "Signaling error");
          setStatus("error");
          return;
        }

        if (msg.type === "room_joined") {
          console.log(
            "[WebRTC] Room joined successfully, waiting for offer..."
          );
          return;
        }

        if (msg.type === "peer_joined") {
          console.log("[WebRTC] Glasses peer joined the room");
          return;
        }

        if (msg.type === "peer_left") {
          console.log("[WebRTC] Peer left, closing PC");
          pcRef.current?.close();
          pcRef.current = null;
          streamRef.current = null;
          if (videoRef.current) {
            videoRef.current.srcObject = null;
          }
          setStatus("connecting");
          return;
        }

        // --- OFFER: create a FRESH PeerConnection here ---
        if (msg.type === "offer") {
          console.log("[WebRTC] Offer received, creating fresh PC...");

          // Close any previous PC from a prior offer
          if (pcRef.current) {
            pcRef.current.close();
            pcRef.current = null;
          }

          try {
            // Fetch TURN credentials
            console.log("[WebRTC] Fetching TURN credentials...");
            const turnRes = await fetch(TURN_ENDPOINT);
            const turnData = await turnRes.json();
            const turnServers: RTCIceServer[] =
              turnData.iceServers || [];
            console.log(
              "[WebRTC] TURN servers:",
              turnServers.length
            );

            // Combine STUN + TURN
            const iceServers = [...STUN_SERVERS, ...turnServers];

            const pc = new RTCPeerConnection({
              iceServers,
              iceCandidatePoolSize: 2,
            });
            pcRef.current = pc;

            // Add recvonly video transceiver so the PC expects incoming video
            pc.addTransceiver("video", { direction: "recvonly" });

            // Store stream on track — but do NOT set srcObject yet
            pc.ontrack = (event) => {
              console.log(
                "[WebRTC] ontrack fired, streams:",
                event.streams.length
              );
              const stream = event.streams[0];
              if (stream) {
                streamRef.current = stream;
              }
            };

            // Attach srcObject only when ICE reaches connected/completed
            pc.oniceconnectionstatechange = () => {
              const state = pc.iceConnectionState;
              console.log("[WebRTC] ICE state:", state);

              if (state === "connected" || state === "completed") {
                console.log("[WebRTC] ICE connected — attaching stream");
                if (videoRef.current && streamRef.current) {
                  videoRef.current.srcObject = streamRef.current;
                }
                setStatus("live");
              }

              if (state === "failed") {
                setError("Connection failed");
                setStatus("error");
              }

              if (state === "disconnected") {
                console.log("[WebRTC] ICE disconnected (may recover)");
              }
            };

            // Forward local ICE candidates to signaling server
            pc.onicecandidate = (event) => {
              if (event.candidate && ws.readyState === WebSocket.OPEN) {
                ws.send(
                  JSON.stringify({
                    type: "candidate",
                    candidate: event.candidate.candidate,
                    sdpMid: event.candidate.sdpMid,
                    sdpMLineIndex: event.candidate.sdpMLineIndex,
                  })
                );
              }
            };

            // Set remote offer
            await pc.setRemoteDescription({
              type: "offer",
              sdp: msg.sdp,
            });

            // Flush any ICE candidates that arrived before the offer
            for (const c of pendingCandidates) {
              await pc.addIceCandidate(c);
            }
            pendingCandidates.length = 0;

            // Create and send answer
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            ws.send(JSON.stringify({ type: "answer", sdp: answer.sdp }));
            console.log("[WebRTC] Answer sent");
          } catch (err) {
            console.error("[WebRTC] Error handling offer:", err);
            setError(
              err instanceof Error ? err.message : "Offer handling failed"
            );
            setStatus("error");
          }
          return;
        }

        // --- ICE CANDIDATE: buffer if no remote description yet ---
        if (msg.type === "candidate") {
          const candidate: RTCIceCandidateInit = {
            candidate: msg.candidate,
            sdpMid: msg.sdpMid,
            sdpMLineIndex: msg.sdpMLineIndex,
          };
          if (pcRef.current?.remoteDescription) {
            await pcRef.current.addIceCandidate(candidate);
          } else {
            pendingCandidates.push(candidate);
          }
        }
      };

      ws.onerror = (e) => {
        console.error("[WebRTC] Signaling error:", e);
        setError("Signaling server connection failed");
        setStatus("error");
      };

      ws.onclose = (e) => {
        console.log(
          "[WebRTC] Signaling closed, code:",
          e.code,
          "reason:",
          e.reason
        );
      };
    },
    [disconnect]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      pcRef.current?.close();
    };
  }, []);

  return { videoRef, status, connect, disconnect, error };
}
