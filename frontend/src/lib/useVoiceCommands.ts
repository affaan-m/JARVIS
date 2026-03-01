"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceStatus = "off" | "listening" | "processing" | "error";

interface VoiceCommand {
  /** The keyword or phrase to match (case-insensitive) */
  trigger: string;
  /** Called when the trigger is detected */
  action: () => void;
}

interface UseVoiceCommandsOptions {
  commands: VoiceCommand[];
  /** Enable/disable listening */
  enabled: boolean;
  /** Called with the raw transcript for display */
  onTranscript?: (text: string) => void;
}

export function useVoiceCommands({
  commands,
  enabled,
  onTranscript,
}: UseVoiceCommandsOptions) {
  const [status, setStatus] = useState<VoiceStatus>("off");
  const [lastCommand, setLastCommand] = useState<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null);
  const commandsRef = useRef(commands);
  commandsRef.current = commands;

  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const start = useCallback(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setStatus("error");
      return;
    }

    // Close any existing instance
    recognitionRef.current?.abort();

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true; // Process interim for faster trigger response
    recognition.lang = "en-US";
    recognition.maxAlternatives = 3;
    recognitionRef.current = recognition;

    recognition.onstart = () => {
      setStatus("listening");
    };

    // Track which commands we've already fired per utterance to avoid double-fire
    const firedForUtterance = new Set<number>();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onresult = (event: any) => {
      const resultIdx = event.results.length - 1;
      const result = event.results[resultIdx];
      const transcript = result[0].transcript.trim().toLowerCase();

      // Update transcript display on every result (interim + final)
      onTranscriptRef.current?.(transcript);

      // Fire command on first match (even interim) for instant response
      if (!firedForUtterance.has(resultIdx)) {
        for (const cmd of commandsRef.current) {
          if (transcript.includes(cmd.trigger.toLowerCase())) {
            firedForUtterance.add(resultIdx);
            setLastCommand(cmd.trigger);
            setStatus("processing");
            cmd.action();
            setTimeout(() => setStatus("listening"), 1500);
            return;
          }
        }
      }
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onerror = (event: any) => {
      if (event.error === "no-speech" || event.error === "aborted") {
        // Non-fatal — restart
        return;
      }
      console.error("[Voice] Recognition error:", event.error);
      setStatus("error");
    };

    recognition.onend = () => {
      // Auto-restart if still enabled (Chrome kills it after ~60s of silence)
      if (recognitionRef.current === recognition) {
        try {
          recognition.start();
        } catch {
          // Already started or page hidden
        }
      }
    };

    try {
      recognition.start();
    } catch {
      setStatus("error");
    }
  }, []);

  const stop = useCallback(() => {
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    setStatus("off");
    setLastCommand(null);
  }, []);

  useEffect(() => {
    if (enabled) {
      start();
    } else {
      stop();
    }
    return () => {
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, [enabled, start, stop]);

  return { status, lastCommand };
}
