import "@/test/mocks";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PhotoCapture } from "../PhotoCapture";

const hooks = vi.hoisted(() => ({
  capture: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  active: { current: false },
  error: { current: null as string | null },
}));
const postPhoto = vi.hoisted(() => vi.fn());

vi.mock("@/lib/usePhotoCapture", () => ({
  usePhotoCapture: () => ({
    videoRef: { current: null },
    active: hooks.active.current,
    error: hooks.error.current,
    start: hooks.start,
    stop: hooks.stop,
    capture: hooks.capture,
  }),
}));

vi.mock("@/lib/gameApi", async () => {
  const actual = await vi.importActual<typeof import("@/lib/gameApi")>("@/lib/gameApi");
  return { ...actual, postPhoto };
});

beforeEach(() => {
  vi.clearAllMocks();
  hooks.active.current = false;
  hooks.error.current = null;
});

describe("PhotoCapture", () => {
  it("says up front that faces are blurred", () => {
    render(<PhotoCapture playerId="p1" hunting={false} onPosted={vi.fn()} />);

    expect(
      screen.getByText(/Alle gezichten worden vervaagd voordat een foto wordt opgeslagen/),
    ).toBeInTheDocument();
  });

  it("starts the camera on request", async () => {
    render(<PhotoCapture playerId="p1" hunting={false} onPosted={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: /CAMERA AAN/ }));

    expect(hooks.start).toHaveBeenCalled();
  });

  it("cannot share while the camera is off", () => {
    render(<PhotoCapture playerId="p1" hunting={false} onPosted={vi.fn()} />);

    expect(screen.getByRole("button", { name: /DELEN/ })).toBeDisabled();
  });

  it("shares a captured photo and reports how many faces were blurred", async () => {
    hooks.active.current = true;
    hooks.capture.mockResolvedValue({ photo_id: "ph_1", faces_blurred: 2, killcam_frames: 0 });
    postPhoto.mockResolvedValue({});
    const onPosted = vi.fn();
    render(<PhotoCapture playerId="p1" hunting={false} onPosted={onPosted} />);

    await userEvent.type(screen.getByLabelText(/Omschrijving bij de foto/), "bij de koffie");
    await userEvent.click(screen.getByRole("button", { name: /DELEN/ }));

    await waitFor(() => expect(postPhoto).toHaveBeenCalledWith("p1", "ph_1", "bij de koffie"));
    expect(onPosted).toHaveBeenCalled();
    expect(await screen.findByText(/2 gezicht\(en\) vervaagd/)).toBeInTheDocument();
  });

  it("explains the fully blurred fallback when no face was found", async () => {
    hooks.active.current = true;
    hooks.capture.mockResolvedValue({ photo_id: "ph_2", faces_blurred: 0, killcam_frames: 0 });
    postPhoto.mockResolvedValue({});
    render(<PhotoCapture playerId="p1" hunting={false} onPosted={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: /DELEN/ }));

    expect(await screen.findByText(/de hele foto is vervaagd/)).toBeInTheDocument();
  });

  it("explains what the killcam keeps before it is switched on", async () => {
    hooks.active.current = true;
    render(<PhotoCapture playerId="p1" hunting onPosted={vi.fn()} />);

    await userEvent.click(screen.getByRole("checkbox", { name: /KILLCAM/ }));

    expect(screen.getByText(/Alleen de\s+laatste vijf blijven staan/)).toBeInTheDocument();
  });

  it("buffers killcam frames only while hunting with it switched on", async () => {
    vi.useFakeTimers();
    hooks.active.current = true;
    hooks.capture.mockResolvedValue({ photo_id: "ph_3", faces_blurred: 0, killcam_frames: 1 });
    const { unmount } = render(<PhotoCapture playerId="p1" hunting={false} onPosted={vi.fn()} />);

    await vi.advanceTimersByTimeAsync(9000);
    expect(hooks.capture).not.toHaveBeenCalled();

    unmount();
    vi.useRealTimers();
  });

  it("surfaces a camera error", () => {
    hooks.error.current = "Geen toegang tot de camera gegeven";
    render(<PhotoCapture playerId="p1" hunting={false} onPosted={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/Geen toegang tot de camera/);
  });
});
