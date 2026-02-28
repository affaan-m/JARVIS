import "@/test/mocks";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

import Home from "@/app/page";
import { demoPersons } from "@/lib/demo-data";

// Mock TopBar to avoid timer side effects
vi.mock("@/components/TopBar", () => ({
  TopBar: ({ personCount }: { personCount: number }) => (
    <div data-testid="topbar">{personCount} SUBJECTS</div>
  ),
}));

describe("Home page", () => {
  it("renders the page with all key sections", () => {
    render(<Home />);

    // TopBar
    expect(screen.getByTestId("topbar")).toBeInTheDocument();

    // Live Feed
    expect(screen.getByText("LIVE FEED")).toBeInTheDocument();

    // Corkboard renders person names
    for (const person of demoPersons) {
      expect(screen.getByText(person.name.toUpperCase())).toBeInTheDocument();
    }
  });

  it("opens dossier for the first person by default", () => {
    render(<Home />);

    // DossierView should show for demoPersons[0]
    expect(screen.getByText("DOSSIER")).toBeInTheDocument();
    expect(screen.getByText(demoPersons[0].name)).toBeInTheDocument();
  });

  it("switches selected person when a different card is clicked", async () => {
    const user = userEvent.setup();
    render(<Home />);

    // Click second person
    const secondPerson = demoPersons[1];
    const secondPersonCard = screen.getByText(secondPerson.name.toUpperCase());
    await user.click(secondPersonCard);

    // DossierView should now show the second person's name
    expect(screen.getByText(secondPerson.name)).toBeInTheDocument();
  });

  it("closes dossier when close button is clicked", async () => {
    const user = userEvent.setup();
    render(<Home />);

    // Dossier should be open initially
    expect(screen.getByText("DOSSIER")).toBeInTheDocument();

    // Click close button
    const closeButton = screen.getByRole("button", { name: /close dossier/i });
    await user.click(closeButton);

    // Dossier should be closed
    expect(screen.queryByText("DOSSIER")).not.toBeInTheDocument();
  });

  it("selects person when a live feed event with personId is clicked", async () => {
    const user = userEvent.setup();
    render(<Home />);

    // Find an activity item that has a personId and click it
    // demoActivity[1] has personId "person_1"
    const activityButtons = screen.getAllByRole("button");
    // The activity buttons are in the LiveFeed, filter out the dossier close button
    const feedButtons = activityButtons.filter(
      (btn) => !btn.getAttribute("aria-label")
    );

    // Click the second feed button (which has personId "person_1")
    await user.click(feedButtons[1]);

    // Should show person_1's dossier (Jordan Vale)
    expect(screen.getByText(demoPersons[0].name)).toBeInTheDocument();
    expect(screen.getByText("DOSSIER")).toBeInTheDocument();
  });
});
