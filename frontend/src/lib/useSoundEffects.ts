"use client";

import { useCallback, useRef } from "react";

export function useSoundEffects() {
  const ctxRef = useRef<AudioContext | null>(null);

  const getCtx = useCallback(() => {
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext();
    }
    if (ctxRef.current.state === "suspended") {
      ctxRef.current.resume();
    }
    return ctxRef.current;
  }, []);

  const playTone = useCallback((freq: number, duration: number, type: OscillatorType = "sine", gain = 0.15) => {
    const ctx = getCtx();
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    g.gain.setValueAtTime(gain, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
    osc.connect(g).connect(ctx.destination);
    osc.start(); osc.stop(ctx.currentTime + duration);
  }, [getCtx]);

  const scannerBeep = useCallback(() => playTone(1200, 0.08, "square", 0.1), [playTone]);

  const targetLock = useCallback(() => {
    playTone(600, 0.12, "sine", 0.12);
    setTimeout(() => playTone(900, 0.15, "sine", 0.12), 130);
  }, [playTone]);

  const successChime = useCallback(() => {
    // C5 → E5 → G5 arpeggio
    playTone(523, 0.15, "sine", 0.1);
    setTimeout(() => playTone(659, 0.15, "sine", 0.1), 120);
    setTimeout(() => playTone(784, 0.2, "sine", 0.1), 240);
  }, [playTone]);

  const sourceFound = useCallback(() => playTone(440, 0.05, "triangle", 0.08), [playTone]);

  return { scannerBeep, targetLock, successChime, sourceFound };
}
