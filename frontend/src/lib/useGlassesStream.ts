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
  connectWebcam: () => void;
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
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [status, setStatus] = useState<StreamStatus>("disconnected");
  const [error, setError] = useState<string | null>(null);

  const clearConnectionTimeout = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    clearConnectionTimeout();
    wsRef.current?.close();
    wsRef.current = null;
    pcRef.current?.close();
    pcRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
    }
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setStatus("disconnected");
    setError(null);
  }, [clearConnectionTimeout]);

  const connectWebcam = useCallback(() => {
    disconnect();
    setStatus("connecting");
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
      .then(stream => {
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setStatus("live");
      })
      .catch(err => {
        console.error("[Webcam] Failed:", err);
        setError(err instanceof Error ? err.message : "Webcam access denied");
        setStatus("error");
      });
  }, [disconnect]);

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
            // Fetch TURN credentials with 5s timeout
            let turnServers: RTCIceServer[] = [];
            try {
              console.log("[WebRTC] Fetching TURN credentials...");
              const turnAbort = new AbortController();
              const turnTimeout = setTimeout(() => turnAbort.abort(), 5000);
              const turnRes = await fetch(TURN_ENDPOINT, { signal: turnAbort.signal });
              clearTimeout(turnTimeout);
              const turnData = await turnRes.json();
              turnServers = turnData.iceServers || [];
              console.log("[WebRTC] TURN response:", JSON.stringify(turnData));
              if (turnServers.length === 0) {
                console.warn("[WebRTC] No TURN servers returned — STUN-only mode");
              }
            } catch (turnErr) {
              console.warn("[WebRTC] TURN fetch failed, continuing with STUN only:", turnErr);
            }

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
                clearConnectionTimeout();
                console.log("[WebRTC] ICE connected — attaching stream");
                if (videoRef.current && streamRef.current) {
                  videoRef.current.srcObject = streamRef.current;
                }
                setStatus("live");
              }

              if (state === "failed") {
                clearConnectionTimeout();
                setError("Connection failed — try a different network");
                setStatus("error");
              }

              if (state === "disconnected") {
                console.log("[WebRTC] ICE disconnected — waiting 5s for recovery");
                clearConnectionTimeout();
                timeoutRef.current = setTimeout(() => {
                  if (pcRef.current?.iceConnectionState === "disconnected") {
                    console.log("[WebRTC] ICE did not recover after 5s");
                    setError("Stream disconnected — connection lost");
                    setStatus("error");
                  }
                }, 5000);
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

            // 20s timeout — if ICE doesn't connect, show error
            clearConnectionTimeout();
            timeoutRef.current = setTimeout(() => {
              const iceState = pcRef.current?.iceConnectionState;
              if (iceState && iceState !== "connected" && iceState !== "completed") {
                console.log("[WebRTC] Connection timed out, ICE state:", iceState);
                setError("Connection timed out — camera may be behind a firewall");
                setStatus("error");
              }
            }, 20000);
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
        const iceState = pcRef.current?.iceConnectionState;
        if (iceState === "connected" || iceState === "completed") {
          // Media flows P2P — signaling loss is fine
          console.log("[WebRTC] Signaling lost but media flows P2P, continuing");
        } else {
          // Signaling was needed for handshake — fatal
          console.log("[WebRTC] Signaling lost during handshake, ICE state:", iceState);
          clearConnectionTimeout();
          setError("Signaling connection lost");
          setStatus("error");
        }
      };
    },
    [disconnect]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearConnectionTimeout();
      wsRef.current?.close();
      pcRef.current?.close();
    };
  }, [clearConnectionTimeout]);

  return { videoRef, status, connect, connectWebcam, disconnect, error };
}
