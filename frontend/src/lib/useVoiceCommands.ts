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
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.maxAlternatives = 3;
    recognitionRef.current = recognition;

    recognition.onstart = () => {
      setStatus("listening");
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onresult = (event: any) => {
      // Only process the latest result
      const result = event.results[event.results.length - 1];
      if (!result.isFinal) return;

      const transcript = result[0].transcript.trim().toLowerCase();
      onTranscriptRef.current?.(transcript);

      // Check each command trigger
      for (const cmd of commandsRef.current) {
        if (transcript.includes(cmd.trigger.toLowerCase())) {
          setLastCommand(cmd.trigger);
          setStatus("processing");
          cmd.action();
          // Reset to listening after brief feedback
          setTimeout(() => setStatus("listening"), 1500);
          return;
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
