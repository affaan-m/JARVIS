import "@/test/mocks";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

import { LiveFeed } from "../LiveFeed";
import { demoActivity } from "@/lib/demo-data";

describe("LiveFeed", () => {
  const defaultProps = {
    activity: demoActivity,
    onEventClick: vi.fn(),
  };

  it("renders heading", () => {
    render(<LiveFeed {...defaultProps} />);
    expect(screen.getByText("LIVE FEED")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE SIGNALS")).toBeInTheDocument();
  });

  it("renders all activity messages", () => {
    render(<LiveFeed {...defaultProps} />);

    for (const item of demoActivity) {
      expect(screen.getByText(item.message)).toBeInTheDocument();
    }
  });

  it("renders agent source labels", () => {
    render(<LiveFeed {...defaultProps} />);

    const itemsWithAgent = demoActivity.filter((a) => a.agentName);
    for (const item of itemsWithAgent) {
      expect(
        screen.getByText(`SOURCE // ${item.agentName!.toUpperCase()}`)
      ).toBeInTheDocument();
    }
  });

  it("calls onEventClick with personId when activity is clicked", async () => {
    const onEventClick = vi.fn();
    const user = userEvent.setup();

    render(<LiveFeed {...defaultProps} onEventClick={onEventClick} />);

    // Click the second activity item (has personId)
    const activityWithPerson = demoActivity.find((a) => a.personId);
    const activityButton = screen.getByText(activityWithPerson!.message).closest("button");
    await user.click(activityButton!);

    expect(onEventClick).toHaveBeenCalledWith(activityWithPerson!.personId);
  });

  it("calls onEventClick with undefined when activity has no personId", async () => {
    const onEventClick = vi.fn();
    const user = userEvent.setup();

    render(<LiveFeed {...defaultProps} onEventClick={onEventClick} />);

    // Click the first activity item (no personId)
    const activityWithoutPerson = demoActivity.find((a) => !a.personId);
    const activityButton = screen.getByText(activityWithoutPerson!.message).closest("button");
    await user.click(activityButton!);

    expect(onEventClick).toHaveBeenCalledWith(undefined);
  });

  it("renders timestamps for all items", () => {
    render(<LiveFeed {...defaultProps} />);

    // All activity items should produce time strings
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBe(demoActivity.length);
  });
});
