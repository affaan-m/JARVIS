import type { ActivityRecord, ConnectionRecord, IntelPerson, PersonRecord } from "./types";

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
      company: "JARVIS",
      workHistory: [
        { role: "Infra Lead", company: "JARVIS", period: "2026-present" },
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
      company: "JARVIS",
      workHistory: [{ role: "Frontend Systems", company: "JARVIS", period: "2026-present" }],
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
      company: "JARVIS",
      workHistory: [{ role: "Research Systems", company: "JARVIS", period: "2026-present" }],
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

export const demoPeople: IntelPerson[] = [
  {
    id: "p1",
    name: "Alex Mercer",
    status: "complete",
    summary: {
      nm: "ALEX MERCER",
      sm: "High-priority intelligence target with cross-sector ties spanning Silicon Valley tech firms and defense contracting networks. Multiple corporate entities registered under associated aliases. Financial footprint suggests diversified asset portfolio with international exposure.",
      title: "Software Engineer",
      location: "San Francisco, CA",
    },
    sources: [
      { nm: "LinkedIn Profile", tp: "SOCIAL", sn: "Software engineer at Google, previously at Meta. 500+ connections with notable defense industry ties." },
      { nm: "County Court Records", tp: "PUBLIC RECORD", sn: "No criminal records found across federal and state databases. One civil filing from 2019 — resolved." },
      { nm: "TechCrunch Feature", tp: "MEDIA", sn: "Featured in Series A funding coverage. Company valued at $12M with Andreessen Horowitz investors." },
      { nm: "SEC Corporate Filing", tp: "CORPORATE", sn: "Listed as board director for three registered LLCs. Two in Delaware, one in Nevada." },
      { nm: "IEEE Research Paper", tp: "ACADEMIC", sn: "Co-authored neural architecture optimization paper. Cited 340 times. Collaborators from MIT and Stanford." },
    ],
  },
  {
    id: "p2",
    name: "Diana Voss",
    status: "complete",
    summary: {
      nm: "DIANA VOSS",
      sm: "Former intelligence analyst turned private consultant. Extensive network in European defense procurement circles. Multiple shell companies traced to Cyprus and Liechtenstein.",
      title: "Private Consultant",
      location: "Berlin, Germany",
    },
    sources: [
      { nm: "Interpol Red Notice DB", tp: "LAW ENFORCEMENT", sn: "No active notices. Historical query flagged from German BKA in 2021 — status unclear." },
      { nm: "Companies House UK", tp: "CORPORATE", sn: "Director of Meridian Consulting Ltd, incorporated 2019. Annual accounts show £2.4M revenue." },
      { nm: "Der Spiegel Article", tp: "MEDIA", sn: "Named in investigative piece on European defense lobbying networks. Denied involvement." },
      { nm: "Property Registry Cyprus", tp: "PUBLIC RECORD", sn: "Two properties registered in Limassol. Combined estimated value €1.8M." },
    ],
  },
  {
    id: "p3",
    name: "Marcus Chen",
    status: "scanning",
    summary: {
      nm: "MARCUS CHEN",
      sm: "Venture capitalist with deep ties to dual-use technology startups. Portfolio includes several companies with known defense contracts.",
      title: "Managing Partner",
      location: "New York, NY",
    },
    sources: [
      {
        nm: "Crunchbase Profile", tp: "CORPORATE",
        sn: "Managing Partner at Apex Ventures. 23 portfolio companies, 4 exits. Focus on AI/ML and cybersecurity.",
        sessionId: "ses_demo_crunchbase", taskId: "tsk_demo_crunchbase_01",
        shareUrl: "https://browser-use.com/share/demo-crunchbase",
        sessionStatus: "completed", url: "https://crunchbase.com/person/marcus-chen",
      },
      {
        nm: "Twitter/X Activity", tp: "SOCIAL",
        sn: "Active in AI policy circles. Recent posts about export control reform and ITAR regulations.",
        sessionId: "ses_demo_twitter", taskId: "tsk_demo_twitter_01",
        sessionStatus: "running", url: "https://twitter.com/search?q=marcus+chen",
      },
    ],
  },
  {
    id: "p4",
    name: "Sarah Okonkwo",
    status: "inactive",
    summary: {
      nm: "SARAH OKONKWO",
      sm: "International trade attorney specializing in sanctions compliance. Previously at the U.S. Treasury Department's OFAC division.",
      title: "Int'l Trade Attorney",
      location: "Washington, D.C.",
    },
    sources: [
      { nm: "DC Bar Association", tp: "PUBLIC RECORD", sn: "Licensed attorney since 2011. No disciplinary actions. Specialization in international trade law." },
    ],
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
