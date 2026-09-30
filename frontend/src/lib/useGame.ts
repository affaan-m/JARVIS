"use client";

// Polls the game state while game mode is on. The player id lives in
// localStorage so a reload keeps you in the game you joined yourself.
import { useCallback, useEffect, useRef, useState } from "react";

import {
  GameOffError,
  type GameSnapshot,
  getMode,
  getState,
  tick,
} from "@/lib/gameApi";

const PLAYER_KEY = "jarvis.game.playerId";
const POLL_MS = 3000;

function readStoredPlayerId(): string | null {
  try {
    return window.localStorage.getItem(PLAYER_KEY);
  } catch {
    return null;
  }
}

export interface UseGameResult {
  enabled: boolean | null;
  snapshot: GameSnapshot | null;
  playerId: string | null;
  error: string | null;
  loading: boolean;
  setPlayerId: (id: string | null) => void;
  refresh: () => Promise<void>;
  setEnabledLocally: (enabled: boolean) => void;
}

export function useGame(): UseGameResult {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [snapshot, setSnapshot] = useState<GameSnapshot | null>(null);
  const [playerId, setPlayerIdState] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const playerIdRef = useRef<string | null>(null);

  useEffect(() => {
    const stored = readStoredPlayerId();
    playerIdRef.current = stored;
    setPlayerIdState(stored);
  }, []);

  const setPlayerId = useCallback((id: string | null) => {
    playerIdRef.current = id;
    setPlayerIdState(id);
    try {
      if (id) window.localStorage.setItem(PLAYER_KEY, id);
      else window.localStorage.removeItem(PLAYER_KEY);
    } catch {
      /* private mode — the id just won't survive a reload */
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const mode = await getMode();
      setEnabled(mode.enabled);
      if (!mode.enabled) {
        setSnapshot(null);
        setError(null);
        return;
      }
      // Advance hint releases and expiries; harmless if another client just did
      await tick().catch(() => undefined);
      const next = await getState(playerIdRef.current ?? undefined);
      setSnapshot(next);
      // Drop a stale id from a wiped game so the join form comes back
      if (playerIdRef.current && !next.me) setPlayerId(null);
      setError(null);
    } catch (err) {
      if (err instanceof GameOffError) {
        setEnabled(false);
        setSnapshot(null);
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : "Onbekende fout");
      }
    } finally {
      setLoading(false);
    }
  }, [setPlayerId]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  return {
    enabled,
    snapshot,
    playerId,
    error,
    loading,
    setPlayerId,
    refresh,
    setEnabledLocally: setEnabled,
  };
}
