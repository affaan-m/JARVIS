"use client";

import { useCallback, useEffect, useRef } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

/** Interval between audio chunk sends (ms). */
const CHUNK_INTERVAL = 3000;

interface UseServerVoiceOptions {
  audioTrack: MediaStreamTrack | null;
  roomCode: string | null;
  enabled: boolean;
  onCommand: (command: string, argument: string | null) => void;
  onTranscript: (text: string) => void;
}

export function useServerVoice({
  audioTrack,
  roomCode,
  enabled,
  onCommand,
  onTranscript,
}: UseServerVoiceOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const onCommandRef = useRef(onCommand);
  onCommandRef.current = onCommand;
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const cleanup = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      try { recorderRef.current.stop(); } catch { /* already stopped */ }
    }
    recorderRef.current = null;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled || !audioTrack || !roomCode) {
      cleanup();
      return;
    }

    const wsUrl = `${WS_BASE}/ws/audio/${roomCode}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[ServerVoice] WS connected:", wsUrl);

      // Build MediaStream from the glasses audio track
      const stream = new MediaStream([audioTrack]);

      // Choose a supported mime type
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
          ws.send(event.data);
        }
      };

      recorder.start(CHUNK_INTERVAL);
      console.log("[ServerVoice] Recording started, chunk interval:", CHUNK_INTERVAL);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "transcript" && msg.text) {
          onTranscriptRef.current(msg.text);
        }
        if (msg.type === "command" && msg.command) {
          onCommandRef.current(msg.command, msg.argument ?? null);
        }
      } catch {
        console.warn("[ServerVoice] Failed to parse WS message");
      }
    };

    ws.onerror = (e) => {
      console.error("[ServerVoice] WS error:", e);
    };

    ws.onclose = () => {
      console.log("[ServerVoice] WS closed");
    };

    return cleanup;
  }, [enabled, audioTrack, roomCode, cleanup]);
}
