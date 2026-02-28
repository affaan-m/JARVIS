import type { ActivityRecord, ConnectionRecord, PersonRecord } from "./types";

export const demoPersons: PersonRecord[] = [
  {
    _id: "person_1",
    name: "Jordan Vale",
    photoUrl: "",
    confidence: 0.94,
    status: "researching",
    boardPosition: { x: 180, y: 140 },
    dossier: {
      summary: "Builder-operator with strong infra instincts and a habit of shipping live demos under time pressure.",
      title: "Infrastructure Lead",
      company: "SPECTER",
      workHistory: [
        { role: "Infra Lead", company: "SPECTER", period: "2026-present" },
        { role: "Full-Stack Engineer", company: "Stealth", period: "2024-2026" },
      ],
      education: [{ school: "UC Berkeley", degree: "B.S. Computer Science" }],
      socialProfiles: {
        github: "github.com/jordanvale",
        linkedin: "linkedin.com/in/jordanvale",
      },
      notableActivity: ["Bootstrapped deployment and CI workflows.", "Prioritizes demo reliability over theory."],
      conversationHooks: ["Ask about high-speed Browser Use pipelines.", "Ask what the fallback demo plan is."],
      riskFlags: ["Needs real Convex project linkage."],
    },
  },
  {
    _id: "person_2",
    name: "Mina Sol",
    photoUrl: "",
    confidence: 0.89,
    status: "identified",
    boardPosition: { x: 620, y: 260 },
    dossier: {
      summary: "Frontend-heavy operator focused on cinematic intelligence-board UX and judge-facing polish.",
      title: "Frontend Systems",
      company: "SPECTER",
      workHistory: [{ role: "Frontend Systems", company: "SPECTER", period: "2026-present" }],
      education: [{ school: "Stanford", degree: "HCI" }],
      socialProfiles: {
        linkedin: "linkedin.com/in/minasol",
        website: "minasol.dev",
      },
      notableActivity: ["Defined the war-room design language.", "Prefers animation with operational meaning."],
      conversationHooks: ["Ask how to make the corkboard feel alive.", "Ask what motion sells the demo best."],
      riskFlags: [],
    },
  },
  {
    _id: "person_3",
    name: "Eli Rowan",
    photoUrl: "",
    confidence: 0.97,
    status: "complete",
    boardPosition: { x: 1020, y: 180 },
    dossier: {
      summary: "Owns synthesis and evaluation flows, with a bias for observability before scale.",
      title: "Research Systems",
      company: "SPECTER",
      workHistory: [{ role: "Research Systems", company: "SPECTER", period: "2026-present" }],
      education: [{ school: "MIT", degree: "AI + Systems" }],
      socialProfiles: {
        github: "github.com/elirowan",
        twitter: "@elirowan",
      },
      notableActivity: ["Mapped eval surfaces before agent implementation.", "Pushes for source attribution and traceability."],
      conversationHooks: ["Ask how Laminar traces should map to dossier confidence.", "Ask where false-positive risk is highest."],
      riskFlags: ["No live Exa key configured yet."],
    },
  },
];

export const demoConnections: ConnectionRecord[] = [
  {
    _id: "connection_1",
    personAId: "person_1",
    personBId: "person_2",
    relationshipType: "design-review",
    description: "Infra + interface handoff on the live board experience.",
  },
  {
    _id: "connection_2",
    personAId: "person_1",
    personBId: "person_3",
    relationshipType: "pipeline-planning",
    description: "Aligning ingestion, observability, and evaluation contracts.",
  },
];

export const demoActivity: ActivityRecord[] = [
  {
    _id: "activity_1",
    type: "capture",
    message: "Foundation pass complete: frontend shell and backend API are online.",
    timestamp: Date.now() - 1000 * 60 * 5,
  },
  {
    _id: "activity_2",
    type: "research",
    message: "Service readiness endpoint exposed for Convex, Exa, Gemini, Laminar, and Telegram.",
    personId: "person_1",
    agentName: "bootstrap",
    timestamp: Date.now() - 1000 * 60 * 3,
  },
  {
    _id: "activity_3",
    type: "complete",
    message: "GitHub Actions scaffolding added for CI, CodeQL, dependency review, and deploy.",
    personId: "person_3",
    agentName: "github",
    timestamp: Date.now() - 1000 * 60,
  },
];
