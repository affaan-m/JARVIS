"use client";

import { GameBoard } from "@/components/game/GameBoard";

export default function GamePage() {
  return (
    <main style={{ minHeight: "100vh", background: "var(--bg-dark)" }}>
      <GameBoard />
    </main>
  );
}
