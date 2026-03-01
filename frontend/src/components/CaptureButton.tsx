"use client";

import { useRef, useState } from "react";
import { Camera, Loader2, CheckCircle, AlertCircle } from "lucide-react";
import { uploadCapture, type CaptureResult } from "@/lib/api";

type CaptureState =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "success"; result: CaptureResult }
  | { kind: "error"; message: string };

export function CaptureButton() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<CaptureState>({ kind: "idle" });

  const handleFile = async (file: File) => {
    setState({ kind: "uploading" });
    try {
      const result = await uploadCapture(file);
      setState({ kind: "success", result });
      // Auto-reset after 4 seconds
      setTimeout(() => setState({ kind: "idle" }), 4000);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setState({ kind: "error", message });
      setTimeout(() => setState({ kind: "idle" }), 4000);
    }
  };

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFile(file);
    }
    // Reset so the same file can be re-selected
    e.target.value = "";
  };

  return (
    <div className="flex items-center gap-2">
      <input
        ref={inputRef}
        type="file"
        accept="image/*,video/*"
        capture="environment"
        className="hidden"
        onChange={onChange}
      />

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={state.kind === "uploading"}
        className="flex items-center gap-1.5 px-3 py-1 rounded text-xs transition-colors"
        style={{
          fontFamily: "var(--font-mono)",
          background: state.kind === "uploading" ? "var(--alert-amber)" : "var(--intel-green)",
          color: "#000",
          opacity: state.kind === "uploading" ? 0.7 : 1,
          cursor: state.kind === "uploading" ? "wait" : "pointer",
        }}
      >
        {state.kind === "uploading" ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : (
          <Camera className="w-3 h-3" />
        )}
        {state.kind === "uploading" ? "UPLOADING..." : "CAPTURE"}
      </button>

      {state.kind === "success" && (
        <span
          className="flex items-center gap-1 text-xs"
          style={{ fontFamily: "var(--font-mono)", color: "var(--intel-green)" }}
        >
          <CheckCircle className="w-3 h-3" />
          {state.result.faces_detected ?? 0} faces &middot; {state.result.persons_created ?? 0} new
        </span>
      )}

      {state.kind === "error" && (
        <span
          className="flex items-center gap-1 text-xs"
          style={{ fontFamily: "var(--font-mono)", color: "var(--stamp-red)" }}
        >
          <AlertCircle className="w-3 h-3" />
          {state.message}
        </span>
      )}
    </div>
  );
}
