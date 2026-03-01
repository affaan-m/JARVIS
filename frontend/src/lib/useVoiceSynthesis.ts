"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface VoiceSynthesisState {
  isSpeaking: boolean;
  transcript: string;
  displayText: string;
}

/**
 * Speaks text aloud using Web Speech API and types it out character-by-character.
 * Triggers when `text` changes to a non-empty value.
 */
export function useVoiceSynthesis() {
  const [state, setState] = useState<VoiceSynthesisState>({
    isSpeaking: false,
    transcript: "",
    displayText: "",
  });

  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const charIdxRef = useRef(0);

  const stop = useCallback(() => {
    if (typeof window !== "undefined") {
      window.speechSynthesis?.cancel();
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    utteranceRef.current = null;
    setState((prev) => ({ ...prev, isSpeaking: false }));
  }, []);

  const speak = useCallback((text: string) => {
    if (!text || typeof window === "undefined" || !window.speechSynthesis) return;

    // Cancel any ongoing speech
    stop();

    const cleaned = text
      .replace(/\*\*/g, "")
      .replace(/\n{2,}/g, ". ")
      .replace(/\n/g, " ")
      .slice(0, 1500);

    setState({ isSpeaking: true, transcript: cleaned, displayText: "" });
    charIdxRef.current = 0;

    // Typewriter effect: reveal characters at ~40 chars/sec
    timerRef.current = setInterval(() => {
      charIdxRef.current += 1;
      if (charIdxRef.current >= cleaned.length) {
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = null;
        setState((prev) => ({ ...prev, displayText: cleaned }));
        return;
      }
      setState((prev) => ({
        ...prev,
        displayText: cleaned.slice(0, charIdxRef.current),
      }));
    }, 25);

    // Speech synthesis — JARVIS is a male AI, use a deep authoritative voice
    const utt = new SpeechSynthesisUtterance(cleaned);
    utt.rate = 0.95;
    utt.pitch = 0.85;
    utt.volume = 1.0;

    // Pick a deep male voice — ranked preference list
    const voices = window.speechSynthesis.getVoices();
    const malePrefs = [
      "Daniel",       // macOS British male — closest to JARVIS
      "Aaron",        // macOS American male
      "Arthur",       // macOS British male
      "Oliver",       // macOS British male
      "Tom",          // macOS male
      "James",        // macOS British male
      "Google UK English Male",  // Chrome
      "Microsoft David",         // Windows male
      "Microsoft Mark",          // Windows male
    ];
    let chosenVoice: SpeechSynthesisVoice | undefined;
    for (const pref of malePrefs) {
      chosenVoice = voices.find((v) => v.name.includes(pref));
      if (chosenVoice) break;
    }
    // Fallback: any English male-sounding voice (avoid "Female", "Karen", "Samantha")
    if (!chosenVoice) {
      const femaleNames = ["samantha", "karen", "victoria", "fiona", "moira", "tessa", "female"];
      chosenVoice = voices.find(
        (v) => v.lang.startsWith("en") && !femaleNames.some((f) => v.name.toLowerCase().includes(f))
      );
    }
    if (!chosenVoice) chosenVoice = voices.find((v) => v.lang.startsWith("en"));
    if (chosenVoice) utt.voice = chosenVoice;

    utt.onend = () => {
      setState((prev) => ({ ...prev, isSpeaking: false }));
    };
    utt.onerror = () => {
      setState((prev) => ({ ...prev, isSpeaking: false }));
    };

    utteranceRef.current = utt;
    window.speechSynthesis.speak(utt);
  }, [stop]);

  // Preload voices (Chrome needs this)
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.speechSynthesis?.getVoices();
    const handler = () => window.speechSynthesis?.getVoices();
    window.speechSynthesis?.addEventListener("voiceschanged", handler);
    return () => {
      window.speechSynthesis?.removeEventListener("voiceschanged", handler);
      stop();
    };
  }, [stop]);

  return { ...state, speak, stop };
}
