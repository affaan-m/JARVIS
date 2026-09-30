"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, Send } from "lucide-react";

import { postPhoto } from "@/lib/gameApi";
import { usePhotoCapture } from "@/lib/usePhotoCapture";

interface PhotoCaptureProps {
  playerId: string;
  /** While true a frame is buffered every few seconds as killcam material. */
  hunting: boolean;
  onPosted: () => void;
}

const KILLCAM_INTERVAL_MS = 4000;

/** Camera for the feed. Faces are blurred on the server before storing. */
export function PhotoCapture({ playerId, hunting, onPosted }: PhotoCaptureProps) {
  const { videoRef, active, error, start, stop, capture } = usePhotoCapture(playerId);
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [killcamOn, setKillcamOn] = useState(false);
  const capturingRef = useRef(false);

  // Buffer a frame now and then so a tag can carry a killcam
  useEffect(() => {
    if (!active || !killcamOn || !hunting) return;
    const id = window.setInterval(() => {
      if (capturingRef.current) return;
      capturingRef.current = true;
      void capture({ killcam: true }).finally(() => {
        capturingRef.current = false;
      });
    }, KILLCAM_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [active, killcamOn, hunting, capture]);

  async function share() {
    setBusy(true);
    setNote(null);
    try {
      const photo = await capture();
      if (!photo) return;
      await postPhoto(playerId, photo.photo_id, caption.trim() || undefined);
      setCaption("");
      setNote(
        photo.faces_blurred > 0
          ? `Gedeeld — ${photo.faces_blurred} gezicht(en) vervaagd.`
          : "Gedeeld — geen gezicht gevonden, de hele foto is vervaagd.",
      );
      onPosted();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      data-testid="photo-capture"
      className="rounded border p-4"
      style={{ borderColor: "rgba(200,214,176,0.15)", background: "rgba(26,32,24,0.85)" }}
    >
      <h3
        className="mb-1 text-sm tracking-[0.2em]"
        style={{ fontFamily: "var(--font-heading)", color: "var(--text-primary)" }}
      >
        CAMERA
      </h3>
      <p className="mb-3 text-xs" style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>
        Alle gezichten worden vervaagd voordat een foto wordt opgeslagen.
      </p>

      <div
        className="mb-3 overflow-hidden rounded"
        style={{ background: "rgba(10,13,8,0.7)", aspectRatio: "4 / 3" }}
      >
        <video
          ref={videoRef}
          data-testid="photo-capture-video"
          muted
          playsInline
          className="h-full w-full object-cover"
          style={{ display: active ? "block" : "none" }}
        />
        {!active && (
          <div
            className="flex h-full items-center justify-center text-xs"
            style={{ color: "var(--text-dim)" }}
          >
            CAMERA UIT
          </div>
        )}
      </div>

      {error && (
        <p role="alert" className="mb-2 text-xs" style={{ color: "var(--accent-red)" }}>
          {error}
        </p>
      )}

      <div className="mb-2 flex flex-wrap gap-2">
        {active ? (
          <button
            type="button"
            onClick={stop}
            className="flex items-center gap-1.5 rounded px-3 py-2 text-xs tracking-widest"
            style={{ border: "1px solid rgba(200,214,176,0.25)", color: "var(--text-ui)" }}
          >
            <CameraOff size={13} /> CAMERA UIT
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void start()}
            className="flex items-center gap-1.5 rounded px-3 py-2 text-xs tracking-widest"
            style={{ background: "var(--intel-green)", color: "#f0f4e8" }}
          >
            <Camera size={13} /> CAMERA AAN
          </button>
        )}

        <label
          className="flex items-center gap-2 rounded px-3 py-2 text-xs tracking-widest"
          style={{ border: "1px solid rgba(200,214,176,0.25)", color: "var(--text-ui)" }}
        >
          <input
            type="checkbox"
            checked={killcamOn}
            onChange={(e) => setKillcamOn(e.target.checked)}
          />
          KILLCAM
        </label>
      </div>

      {killcamOn && (
        <p className="mb-2 text-[11px]" style={{ color: "var(--alert-amber)" }}>
          Er wordt elke {KILLCAM_INTERVAL_MS / 1000} seconden een beeld bewaard. Alleen de
          laatste vijf blijven staan, en ze verschijnen pas als je een tag claimt.
        </p>
      )}

      <div className="flex gap-2">
        <input
          value={caption}
          onChange={(e) => setCaption(e.target.value)}
          maxLength={280}
          placeholder="Wat zie je?"
          aria-label="Omschrijving bij de foto"
          className="min-w-0 flex-1 rounded border px-2 py-1.5 text-xs"
          style={{
            background: "rgba(10,13,8,0.7)",
            borderColor: "rgba(200,214,176,0.2)",
            color: "var(--text-primary)",
          }}
        />
        <button
          type="button"
          onClick={() => void share()}
          disabled={!active || busy}
          className="flex items-center gap-1.5 rounded px-3 py-2 text-xs tracking-widest disabled:opacity-40"
          style={{ background: "var(--pin-gold)", color: "#1a1a1a" }}
        >
          <Send size={13} /> {busy ? "BEZIG..." : "DELEN"}
        </button>
      </div>

      {note && (
        <p className="mt-2 text-xs" style={{ color: "var(--intel-green)" }}>
          {note}
        </p>
      )}
    </section>
  );
}
