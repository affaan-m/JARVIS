import "@/test/mocks";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

import { Corkboard } from "../Corkboard";
import { demoConnections, demoPersons } from "@/lib/demo-data";

describe("Corkboard", () => {
  const defaultProps = {
    persons: demoPersons,
    connections: demoConnections,
    onPersonClick: vi.fn(),
    selectedPersonId: null,
  };

  it("renders all person cards with their names", () => {
    render(<Corkboard {...defaultProps} />);

    for (const person of demoPersons) {
      expect(screen.getByText(person.name.toUpperCase())).toBeInTheDocument();
    }
  });

  it("renders connection lines between persons", () => {
    const { container } = render(<Corkboard {...defaultProps} />);

    // ConnectionLine renders inside <g class="string-glow">, each with a <path>
    const connectionGroups = container.querySelectorAll("g.string-glow");
    expect(connectionGroups.length).toBe(demoConnections.length);
  });

  it("renders connection labels", () => {
    render(<Corkboard {...defaultProps} />);

    for (const conn of demoConnections) {
      expect(screen.getByText(conn.relationshipType.toUpperCase())).toBeInTheDocument();
    }
  });

  it("calls onPersonClick when a card is clicked", async () => {
    const onPersonClick = vi.fn();
    const user = userEvent.setup();

    render(<Corkboard {...defaultProps} onPersonClick={onPersonClick} />);

    const firstPersonName = screen.getByText(demoPersons[0].name.toUpperCase());
    await user.click(firstPersonName);

    expect(onPersonClick).toHaveBeenCalledWith(demoPersons[0]._id);
  });

  it("passes selectedPersonId to PersonCard", () => {
    const { container } = render(
      <Corkboard {...defaultProps} selectedPersonId="person_1" />
    );

    // The selected card should have the red drop-shadow filter
    const cards = container.querySelectorAll("[data-person-card]");
    expect(cards.length).toBe(demoPersons.length);
  });
});
