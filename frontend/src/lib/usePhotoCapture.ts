"use client";

// Grabs a still from the player's camera for the game feed and the killcam.
// Faces are blurred server-side before the photo is stored, so nothing
// unblurred ever leaves this browser's memory.
import { useCallback, useEffect, useRef, useState } from "react";

import { uploadPhoto, type UploadedPhoto } from "@/lib/gameApi";

const JPEG_QUALITY = 0.8;
const MAX_EDGE = 1280;

export interface UsePhotoCaptureResult {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  active: boolean;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
  capture: (options?: { killcam?: boolean }) => Promise<UploadedPhoto | null>;
}

export function usePhotoCapture(playerId: string | null): UsePhotoCaptureResult {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setActive(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }
      setActive(true);
    } catch (err) {
      setError(
        err instanceof Error && err.name === "NotAllowedError"
          ? "Geen toegang tot de camera gegeven"
          : "Camera kon niet gestart worden",
      );
      setActive(false);
    }
  }, []);

  const capture = useCallback(
    async ({ killcam = false }: { killcam?: boolean } = {}) => {
      const video = videoRef.current;
      if (!video || !video.videoWidth) return null;

      const scale = Math.min(1, MAX_EDGE / Math.max(video.videoWidth, video.videoHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      const context = canvas.getContext("2d");
      if (!context) return null;
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
      try {
        return await uploadPhoto(dataUrl, { playerId: playerId ?? undefined, killcam });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Uploaden mislukte");
        return null;
      }
    },
    [playerId],
  );

  useEffect(() => stop, [stop]);

  return { videoRef, active, error, start, stop, capture };
}
