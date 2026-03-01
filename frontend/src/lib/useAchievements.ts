"use client";

import { useCallback, useRef, useState } from "react";

export interface Achievement {
  id: string;
  label: string;
  icon: string;
}

const ACHIEVEMENTS: Record<string, Achievement> = {
  FIRST_TARGET: { id: "FIRST_TARGET", label: "FIRST TARGET ACQUIRED", icon: "\uD83C\uDFAF" },
  INTEL_COMPLETE: { id: "INTEL_COMPLETE", label: "INTEL COMPLETE", icon: "\u2705" },
  COMBO_5X: { id: "COMBO_5X", label: "5x COMBO", icon: "\u26A1" },
  DEEP_INTEL: { id: "DEEP_INTEL", label: "DEEP INTEL", icon: "\uD83D\uDD0D" },
  MULTI_TARGET: { id: "MULTI_TARGET", label: "MULTI-TARGET", icon: "\uD83D\uDC65" },
};

export function useAchievements() {
  const [toast, setToast] = useState<Achievement | null>(null);
  const firedRef = useRef<Set<string>>(new Set());
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fireAchievement = useCallback((id: string) => {
    if (firedRef.current.has(id)) return;
    const ach = ACHIEVEMENTS[id];
    if (!ach) return;
    firedRef.current.add(id);
    setToast(ach);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setToast(null), 3500);
  }, []);

  return { toast, fireAchievement };
}
