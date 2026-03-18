# System Architecture: JARVIS
## Real-Time Person Intelligence Platform

**Version:** 0.1 | **Date:** 2026-02-27

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        JARVIS ARCHITECTURE                        │
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────────────────┐ │
│  │  META     │───▶│  CAPTURE     │───▶│    IDENTIFICATION         │ │
│  │  GLASSES  │    │  SERVICE     │    │    (PimEyes + Vision LLM) │ │
│  └──────────┘    └──────────────┘    └───────────┬───────────────┘ │
│                                                   │                 │
│                                                   ▼                 │
│                                      ┌───────────────────────────┐ │
│                                      │   ORCHESTRATOR            │ │
│                                      │   (Agent Swarm Manager)   │ │
│                                      └───────────┬───────────────┘ │
│                                                   │                 │
│                         ┌─────────────────────────┼────────────┐   │
│                         ▼            ▼            ▼            ▼   │
│                    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐│
│                    │LinkedIn │ │ X/Twitter│ │Instagram│ │  Exa   ││
│                    │ Agent   │ │  Agent   │ │  Agent  │ │  API   ││
│                    └────┬────┘ └────┬────┘ └────┬────┘ └───┬────┘│
│                         │           │           │          │      │
│                         └─────────┬─┴───────────┴──────────┘      │
│                                   ▼                                │
│                      ┌────────────────────────┐                    │
│                      │   REPORT SYNTHESIZER   │                    │
│                      │   (LLM Aggregation)    │                    │
│                      └──────────┬─────────────┘                    │
│                                 │                                   │
│                    ┌────────────┼────────────┐                     │
│                    ▼            ▼            ▼                     │
│              ┌──────────┐ ┌──────────┐ ┌──────────────┐           │
│              │ Convex   │ │ MongoDB  │ │  Corkboard   │           │
│              │ Realtime │ │ Storage  │ │  Frontend    │           │
│              └──────────┘ └──────────┘ └──────────────┘           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  OBSERVABILITY: Laminar (tracing) + HUD (agent debugging)   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. Component Deep Dive

### 2.1 Capture Service

**Purpose:** Receive photos from Meta glasses, preprocess, and forward to identification pipeline.

**Input:** JPEG/PNG image from Meta glasses camera
**Output:** Processed image + metadata (timestamp, location if available)

```
Meta Glasses
    │
    ├── Option A: Telegram Bot (glasses can send photos via Telegram)
    ├── Option B: HTTP endpoint (glasses web app → POST /capture)
    └── Option C: Polling service (check glasses photo stream)

    ▼
┌─────────────────────────┐
│ Capture Service (Python) │
│                          │
│ - Receive image          │
│ - Validate & resize      │
│ - Generate capture_id    │
│ - Store raw in MongoDB   │
│ - Emit to Convex         │
│ - Forward to ID pipeline │
└─────────────────────────┘
```

**Tech choice:** Python FastAPI — Edmund's existing code is Python, fastest to extend.

### 2.2 Identification Pipeline

**Purpose:** Identify who the person is from their photo.

```
┌───────────────────────────────────────────────────┐
│              IDENTIFICATION PIPELINE               │
│                                                     │
│  Image ──▶ PimEyes Search ──▶ Results              │
│                │                    │               │
│                │ (parallel          │               │
│                │  accounts          ▼               │
│                │  for anti-bot) ┌────────────┐     │
│                │                │ Vision LLM │     │
│                │                │ (GPT-4o)   │     │
│                │                │            │     │
│                │                │ Extract:   │     │
│                │                │ - Name     │     │
│                │                │ - Context  │     │
│                │                │ - URLs     │     │
│                │                └─────┬──────┘     │
│                │                      │             │
│                │                      ▼             │
│                │               Initial Report       │
│                │               (name, photo URLs,    │
│                │                likely profiles)     │
└───────────────┴──────────────────────┬──────────────┘
                                       │
                                       ▼
                              Orchestrator
```

**Anti-bot strategy for PimEyes:**
- Pool of 3-5 PimEyes accounts
- Round-robin assignment per search
- Rate limit: max 1 search per account per 30 seconds
- If blocked: rotate to next account, exponential backoff
- Use Daytona sandboxes for isolated browser sessions

### 2.3 Agent Swarm Orchestrator

**Purpose:** Coordinate multiple Browser Use agents to research a person in parallel.

```
┌──────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                                │
│                                                                │
│  Input: Initial Report (name, photo URLs, likely profiles)    │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                 AGENT POOL (Browser Use)                 │  │
│  │                                                          │  │
│  │  Agent 1: LinkedIn    ──▶ Profile, experience, skills   │  │
│  │  Agent 2: X/Twitter   ──▶ Tweets, followers, bio        │  │
│  │  Agent 3: Instagram   ──▶ Posts, followers, bio          │  │
│  │  Agent 4: Facebook    ──▶ Friends, education, work      │  │
│  │  Agent 5: Google      ──▶ News, articles, mentions      │  │
│  │  Agent 6: GitHub      ──▶ Repos, contributions          │  │
│  │                                                          │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                 API ENRICHMENT (parallel)                │  │
│  │                                                          │  │
│  │  Exa API      ──▶ Structured person/company data        │  │
│  │  Supermemory  ──▶ Cross-session memory context          │  │
│  │                                                          │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  Coordination:                                                 │
│  - Each agent runs independently                              │
│  - Results stream to Convex as they arrive                    │
│  - Orchestrator tracks completion state per person            │
│  - Timeout: 3 minutes per person, partial results OK          │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

**Browser Use Integration:**
```python
# Pseudocode for agent deployment
from browser_use import Agent, Browser

async def research_person(person_id, initial_report):
    tasks = [
        research_linkedin(person_id, initial_report),
        research_twitter(person_id, initial_report),
        research_instagram(person_id, initial_report),
        research_google(person_id, initial_report),
    ]
    # Run all agents in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Stream partial results as they complete
    for result in results:
        await stream_to_convex(person_id, result)
```

### 2.4 Report Synthesizer

**Purpose:** Aggregate all gathered data into a coherent dossier.

```
All Agent Results (per person)
    │
    ▼
┌────────────────────────────────────┐
│       REPORT SYNTHESIZER           │
│                                     │
│  Input: Raw data from all agents   │
│                                     │
│  LLM (Gemini/GPT-4o):             │
│  - Deduplicate information         │
│  - Cross-reference for accuracy    │
│  - Generate structured dossier:    │
│    {                               │
│      name, title, company,         │
│      photo_url, confidence_score,  │
│      summary (2-3 sentences),      │
│      work_history [],              │
│      education [],                 │
│      social_profiles {},           │
│      notable_activity [],          │
│      connections_to_others [],     │
│      conversation_hooks [],        │
│      risk_flags []                 │
│    }                               │
│                                     │
│  Laminar: trace every synthesis    │
│  for accuracy verification         │
└──────────────┬─────────────────────┘
               │
               ▼
    Convex (real-time) + MongoDB (persistent)
```

### 2.5 Real-Time Data Layer

**Purpose:** Power real-time UI updates as intel streams in.

```
┌──────────────────────────────────────────────┐
│           CONVEX REAL-TIME DATABASE           │
│                                               │
│  Tables:                                      │
│  ┌─────────────────────────────────────────┐ │
│  │ captures                                 │ │
│  │ - capture_id, image_url, timestamp       │ │
│  │ - status: pending|identifying|researching│ │
│  │ - person_id (once identified)            │ │
│  └─────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────┐ │
│  │ persons                                  │ │
│  │ - person_id, name, photo_url             │ │
│  │ - confidence_score                        │ │
│  │ - status: identified|researching|complete│ │
│  │ - dossier (JSON, grows over time)        │ │
│  │ - position {x, y} on corkboard          │ │
│  └─────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────┐ │
│  │ connections                              │ │
│  │ - person_a_id, person_b_id              │ │
│  │ - relationship_type, description         │ │
│  └─────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────┐ │
│  │ intel_fragments                          │ │
│  │ - person_id, source, data_type           │ │
│  │ - content (raw), timestamp               │ │
│  │ - verified: boolean                      │ │
│  └─────────────────────────────────────────┘ │
│                                               │
│  Subscriptions:                               │
│  - Frontend subscribes to persons table       │
│  - New fragments trigger dossier re-render    │
│  - Connection changes trigger draw-strings    │
└──────────────────────────────────────────────┘
```

**Why Convex over just MongoDB:**
- Convex gives us real-time subscriptions out of the box — no WebSocket setup
- Frontend auto-updates when data changes — critical for the streaming corkboard effect
- MongoDB for persistent/archival storage, Convex for live session state

### 2.6 Corkboard Frontend

**Purpose:** The money shot. FBI/COD-style mission board that makes judges go "holy shit."

```
┌──────────────────────────────────────────────────────────────────┐
│                    CORKBOARD FRONTEND                             │
│                    (Next.js + Vercel)                             │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                                                             │  │
│  │    ┌─────┐         ┌─────┐                                 │  │
│  │    │Photo│─ ─ ─ ─ ─│Photo│     Cork texture background     │  │
│  │    │ + ??│         │ + ??│     Pin/tack aesthetic           │  │
│  │    └──┬──┘         └──┬──┘     Papers "spawn in" with      │  │
│  │       │    string     │        animation                    │  │
│  │       └──────┬────────┘        Red string connections       │  │
│  │              │                                              │  │
│  │         ┌────┴────┐                                        │  │
│  │         │  Photo  │                                        │  │
│  │         │  Name   │   ◄── Click to zoom into dossier      │  │
│  │         │  Title  │                                        │  │
│  │         └─────────┘                                        │  │
│  │                                                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Tech: React + Framer Motion (animations) + Tailwind             │
│  State: Convex useQuery() subscriptions                          │
│  Deploy: Vercel                                                   │
│                                                                   │
│  Views:                                                           │
│  1. Corkboard (main) — all people as pinned papers               │
│  2. Dossier (zoom) — full intel on one person                    │
│  3. Relationship Graph — connections visualization               │
│  4. Live Feed — streaming activity log                           │
└──────────────────────────────────────────────────────────────────┘
```

**Animation Spec:**
- New person: paper slides in from offscreen, pins to board with a bounce
- New connection: red string draws between two papers
- Intel update: paper glows briefly, data refreshes
- Loading state: paper has "CLASSIFIED" stamp, gradually reveals content

## 3. Data Flow (End-to-End)

```
1. CAPTURE
   Meta Glasses → [photo] → Capture Service → MongoDB (raw image)
                                             → Convex (capture record, status: "pending")

2. IDENTIFY
   Capture Service → PimEyes (via Browser Use agent, rotating accounts)
                   → Vision LLM (extract name, URLs from PimEyes results)
                   → Convex (person record, status: "identified")
                   → Frontend: paper appears on corkboard with photo + name

3. DEEP RESEARCH
   Orchestrator → spawn 4-6 Browser Use agents per person
               → each agent: navigate site → extract data → POST to API
               → API → Convex (intel_fragments table)
               → Frontend: paper updates in real-time as data arrives

4. SYNTHESIZE
   Orchestrator (on agent completion or timeout) → LLM synthesis
               → Convex (person.dossier updated, status: "complete")
               → Convex (connections table updated)
               → Frontend: paper fully revealed, strings drawn

5. NOTIFY
   Synthesizer → Telegram bot → Meta glasses notification
              → Web overlay (accessible on glasses browser)
```

## 4. API Contracts

### POST /api/capture
```json
// Request
{ "image": "base64_encoded_jpeg", "timestamp": "ISO8601", "source": "meta_glasses" }

// Response
{ "capture_id": "uuid", "status": "processing" }
```

### GET /api/person/:id
```json
// Response
{
  "person_id": "uuid",
  "name": "John Smith",
  "confidence": 0.92,
  "photo_url": "https://...",
  "status": "researching",
  "dossier": {
    "summary": "CTO at Acme Corp, previously at Google...",
    "work_history": [...],
    "education": [...],
    "social_profiles": { "linkedin": "...", "twitter": "..." },
    "notable_activity": [...],
    "conversation_hooks": ["Ask about their recent Series B", "Shared connection: ..."],
    "risk_flags": []
  },
  "connections": [{ "person_id": "uuid", "type": "coworker", "description": "..." }]
}
```

### Convex Subscriptions (Frontend)
```typescript
// Real-time person list
const persons = useQuery(api.persons.list);

// Real-time intel fragments for a person
const intel = useQuery(api.intel.byPerson, { personId });

// Real-time connections
const connections = useQuery(api.connections.all);
```

## 5. Tech Stack Summary

| Layer | Technology | Reason |
|-------|-----------|--------|
| **Glasses Integration** | Meta Ray-Ban + Telegram Bot | Simplest photo capture path |
| **Backend** | Python (FastAPI) | Edmund's existing code, Browser Use SDK is Python |
| **Agent Orchestration** | Browser Use API + Python asyncio | Core sponsor, required for hackathon |
| **LLM** | GPT-4o (vision) + Gemini (synthesis) | Vision for photos, Gemini for cheap text synthesis |
| **Real-time DB** | Convex | Real-time subscriptions, zero WebSocket setup |
| **Persistent DB** | MongoDB Atlas | Free cluster, good for document storage |
| **Research API** | Exa | Structured web research, fast |
| **Frontend** | Next.js + React + Framer Motion + Tailwind | Fast to build, great animations, Vercel deploy |
| **Hosting** | Vercel (frontend) + Daytona (agent sandboxes) | Sponsor credits available |
| **Observability** | Laminar (tracing) + HUD (debugging) | Verify accuracy, debug agents |
| **Memory** | Supermemory | Cross-session agent memory |

## 6. Key Trade-offs

| Decision | Alternative | Why This Way |
|----------|-------------|-------------|
| Convex for real-time vs WebSockets | Raw WS + MongoDB Change Streams | Convex = zero boilerplate, real-time subscriptions out of the box. 24hr hackathon, speed > flexibility |
| Python backend vs Node.js | Full JS stack | Edmund's code is Python, Browser Use SDK is Python. Don't rewrite. |
| Multiple PimEyes accounts vs single | Queue + rate limit on one account | Single account will get blocked. Multiple = parallel + resilience. |
| Streaming partial results vs wait-for-complete | Batch results | Streaming = better demo. Judges see data appearing live. Way more impressive. |
| Gemini for synthesis vs GPT-4o for everything | Single model | Gemini is cheap ($20 credits), save GPT-4o budget for vision tasks where it's better. |

## 7. Deployment Architecture (Hackathon)

```
┌──────────────────────────────────────┐
│  Vercel                               │
│  - Next.js frontend (corkboard)      │
│  - API routes (capture endpoint)     │
└──────────────────┬───────────────────┘
                   │
┌──────────────────┼───────────────────┐
│  Daytona Sandbox(es)                  │
│  - Python backend (FastAPI)          │
│  - Browser Use agents (headless)     │
│  - PimEyes automation                │
│  - Agent orchestrator                │
└──────────────────┬───────────────────┘
                   │
┌──────────────────┼───────────────────┐
│  Managed Services                     │
│  - Convex (real-time DB)             │
│  - MongoDB Atlas (persistent)        │
│  - Laminar (observability)           │
│  - Exa API (research)               │
│  - OpenAI API (vision + synthesis)   │
│  - Google Gemini API (synthesis)     │
└──────────────────────────────────────┘
```

## 8. Risk Mitigations (Technical)

**PimEyes blocks us:**
- Fallback: Google Reverse Image Search via Browser Use agent
- Fallback: Manual name entry as override

**Browser Use agents too slow:**
- Pre-warm browser sessions
- Cache common profile templates
- Timeout at 3 min, serve partial results

**LLM hallucinations produce wrong info:**
- Laminar traces on every synthesis call
- Confidence scoring on each data point
- Source attribution (link to where data came from)
- Red flag if conflicting information found

**Demo fails live:**
- Pre-record backup video (required by rules anyway)
- Have 2-3 people pre-researched as "warm cache"
- Manual trigger fallback if glasses pipeline fails
