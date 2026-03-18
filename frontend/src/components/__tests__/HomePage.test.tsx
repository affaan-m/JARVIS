import "@/test/mocks";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import Home from "@/app/page";

// IntelBoard is a complex component that requires Convex, browser media APIs,
// WebSockets, and audio — all unavailable in jsdom. The page itself is a
// one-liner wrapper; test that it mounts and delegates to IntelBoard.
vi.mock("@/components/IntelBoard", () => ({
  default: () => <div data-testid="intel-board">INTEL BOARD</div>,
}));

describe("Home page", () => {
  it("renders IntelBoard", () => {
    render(<Home />);
    expect(screen.getByTestId("intel-board")).toBeInTheDocument();
  });
});
