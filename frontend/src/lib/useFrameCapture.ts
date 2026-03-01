"use client";

import { useCallback, useEffect, useRef } from "react";

export interface Detection {
  bbox: [number, number, number, number];
  confidence: number;
  track_id: number | null;
}

export interface FaceIdentification {
  track_id: number;
  status: "identifying" | "identified" | "failed";
  name: string | null;
  person_id: string | null;
}

export interface FrameCaptureResponse {
  capture_id: string;
  detections: Detection[];
  new_persons: number;
  identifications: FaceIdentification[];
  timestamp: number;
  source: string;
}

interface UseFrameCaptureOptions {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  enabled: boolean;
  intervalMs?: number;
  backendUrl?: string;
  onCapture?: (response: FrameCaptureResponse) => void;
}

const DEFAULT_INTERVAL = 2500;
const DEFAULT_BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useFrameCapture({
  videoRef,
  enabled,
  intervalMs = DEFAULT_INTERVAL,
  backendUrl = DEFAULT_BACKEND,
  onCapture,
}: UseFrameCaptureOptions) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const captureAndSend = useCallback(async () => {
    const video = videoRef.current;
    if (!video || video.readyState < 2) return;

    if (!canvasRef.current) {
      canvasRef.current = document.createElement("canvas");
    }
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(video, 0, 0);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.8);
    const base64 = dataUrl.split(",")[1];

    try {
      const res = await fetch(`${backendUrl}/api/capture/frame`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          frame: base64,
          timestamp: Date.now(),
          source: "glasses_stream",
        }),
      });
      if (res.ok) {
        const data: FrameCaptureResponse = await res.json();
        onCapture?.(data);
      }
    } catch {
      // Silently fail — backend may be down, don't crash the UI
    }
  }, [videoRef, backendUrl, onCapture]);

  useEffect(() => {
    if (enabled) {
      captureAndSend();
      intervalRef.current = setInterval(captureAndSend, intervalMs);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [enabled, intervalMs, captureAndSend]);
}
