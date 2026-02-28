import "@/test/mocks";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

import { DossierView } from "../DossierView";
import { demoPersons } from "@/lib/demo-data";

describe("DossierView", () => {
  const person = demoPersons[0]; // Jordan Vale, has full dossier
  const defaultProps = {
    person,
    onClose: vi.fn(),
  };

  it("renders person name", () => {
    render(<DossierView {...defaultProps} />);
    expect(screen.getByText(person.name)).toBeInTheDocument();
  });

  it("renders dossier label", () => {
    render(<DossierView {...defaultProps} />);
    expect(screen.getByText("DOSSIER")).toBeInTheDocument();
  });

  it("renders title and company", () => {
    render(<DossierView {...defaultProps} />);
    expect(
      screen.getByText(`${person.dossier!.title} // ${person.dossier!.company}`)
    ).toBeInTheDocument();
  });

  it("renders summary", () => {
    render(<DossierView {...defaultProps} />);
    expect(screen.getByText(person.dossier!.summary)).toBeInTheDocument();
  });

  it("renders work history entries", () => {
    render(<DossierView {...defaultProps} />);
    for (const entry of person.dossier!.workHistory) {
      expect(screen.getByText(entry.role)).toBeInTheDocument();
    }
  });

  it("renders education entries", () => {
    render(<DossierView {...defaultProps} />);
    for (const entry of person.dossier!.education) {
      expect(screen.getByText(entry.school)).toBeInTheDocument();
    }
  });

  it("renders conversation hooks", () => {
    render(<DossierView {...defaultProps} />);
    for (const hook of person.dossier!.conversationHooks) {
      expect(screen.getByText(`• ${hook}`)).toBeInTheDocument();
    }
  });

  it("renders risk flags", () => {
    render(<DossierView {...defaultProps} />);
    for (const flag of person.dossier!.riskFlags) {
      expect(screen.getByText(`• ${flag}`)).toBeInTheDocument();
    }
  });

  it("renders social profile links", () => {
    render(<DossierView {...defaultProps} />);
    const profiles = person.dossier!.socialProfiles;
    for (const key of Object.keys(profiles)) {
      const value = profiles[key as keyof typeof profiles];
      if (value) {
        expect(screen.getByText(key.toUpperCase())).toBeInTheDocument();
      }
    }
  });

  it("calls onClose when close button is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();

    render(<DossierView {...defaultProps} onClose={onClose} />);

    const closeButton = screen.getByRole("button", { name: /close dossier/i });
    await user.click(closeButton);

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("shows fallback text when no dossier is present", () => {
    const personWithoutDossier = {
      ...demoPersons[1],
      dossier: undefined,
    };

    render(<DossierView person={personWithoutDossier} onClose={vi.fn()} />);

    expect(screen.getByText("No synthesized dossier yet.")).toBeInTheDocument();
    expect(screen.getByText("Unknown role")).toBeInTheDocument();
  });
});
