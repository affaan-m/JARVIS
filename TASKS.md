# JARVIS — Build Tasks
## Ordered by critical path. Check off as you go.

---

### PHASE 1: Foundation (Hours 0-4)

- [ ] **T01: Convex project setup**
  - `npx create-convex` in frontend/
  - Copy schema from TECH_DOC.md → `convex/schema.ts`
  - Create mutations: `persons.create`, `persons.update`, `captures.create`
  - Create queries: `persons.listAll`, `persons.getById`, `connections.listAll`, `intel.recentActivity`
  - Verify with `npx convex dev` — should deploy without errors
  - **Acceptance:** Can create + query a person from Convex dashboard

- [x] **T02: FastAPI skeleton**
  - `pip install fastapi uvicorn python-dotenv pydantic-settings`
  - Create `backend/main.py` with `/api/health`, `/api/capture` stubs
  - Create `backend/config.py` with Settings class (see SYSTEM_DESIGN.md §8)
  - Create `.env` from `.env.example`
  - **Acceptance:** `uvicorn main:app --reload` starts, `/api/health` returns OK

- [x] **T03: Next.js project setup**
  - `npx create-next-app frontend --typescript --tailwind --app`
  - Install: `framer-motion`, `convex`, `@use-gesture/react`, `lucide-react`
  - Add Google Fonts (Bebas Neue, Courier Prime, Inter) to layout.tsx
  - Add CSS variables from DESIGN_HANDOFF.md §1 to globals.css
  - Wire up Convex provider in layout.tsx
  - **Acceptance:** `npm run dev` shows page with correct fonts

- [ ] **T04: Convex ↔ Frontend proof of life**
  - Create a test button that inserts a dummy person via Convex mutation
  - Display the person's name on the page via `useQuery`
  - Verify real-time: change data in Convex dashboard → page updates instantly
  - **Acceptance:** Button click → name appears in <1 second

---

### PHASE 2: Identification Pipeline (Hours 4-8)

- [ ] **T05: PimEyes Browser Use agent**
  - Create `backend/identification/pimeyes.py` (see SYSTEM_DESIGN.md §2.3)
  - Implement `PimEyesSearcher` class with Browser Use SDK
  - Navigate to pimeyes.com, upload image, extract results page screenshot
  - Use Gemini 2.0 Flash to parse screenshot → names + URLs
  - **Acceptance:** Given a face photo, returns [{name, confidence, urls}]

- [ ] **T06: Account pool rotation**
  - Create `backend/identification/pool.py` (see SYSTEM_DESIGN.md §2.4)
  - Implement `AccountPool` with 3+ PimEyes accounts
  - 30-second cooldown per account, round-robin selection
  - **Acceptance:** 5 sequential searches use different accounts, no rate limits

- [ ] **T07: Capture service + Telegram bot**
  - Create `backend/capture/service.py` (see SYSTEM_DESIGN.md §1.3)
  - Create `backend/capture/telegram_bot.py` (see SYSTEM_DESIGN.md §1.4)
  - ffmpeg frame extraction from video
  - mediapipe face detection on extracted frames
  - POST detected faces to `/api/capture`
  - **Acceptance:** Send video to Telegram bot → faces detected → Convex shows new capture

- [ ] **T08: End-to-end identification pipeline**
  - Wire together: capture → PimEyes → Gemini parse → create Person in Convex
  - Test with a real photo of a known person
  - **Acceptance:** Upload photo → Person card appears in Convex with name + confidence

---

### PHASE 3: Agent Swarm (Hours 8-14)

- [ ] **T09: Exa fast-pass enrichment**
  - Create `backend/enrichment/exa_client.py` (see SYSTEM_DESIGN.md §3.4)
  - Search person name + context → extract LinkedIn URL, company, title
  - Write results as intel fragments to Convex
  - **Acceptance:** Name search returns structured person data in <500ms

- [ ] **T10: LinkedIn Browser Use agent**
  - Create `backend/agents/linkedin_agent.py` (see SYSTEM_DESIGN.md §3.2)
  - Navigate to LinkedIn profile URL (from Exa or PimEyes)
  - Extract: headline, about, experience, education, skills, recent posts
  - Use Voyager API interception where possible for speed
  - **Acceptance:** Given LinkedIn URL → returns structured profile data

- [ ] **T11: Twitter/X agent (twscrape)**
  - Create `backend/agents/twitter_agent.py` (see SYSTEM_DESIGN.md §3.3)
  - Use twscrape for reverse GraphQL extraction
  - Fallback to Browser Use if twscrape fails
  - Extract: bio, recent tweets, followers, engagement
  - **Acceptance:** Given Twitter handle → returns structured profile + recent tweets

- [ ] **T12: Google search agent**
  - Create `backend/agents/google_agent.py`
  - Browser Use agent: search "{name} {company}" on Google
  - Extract top 5 result titles + snippets
  - Feed into Exa for deeper page-level extraction if relevant
  - **Acceptance:** Returns relevant search results for a person

- [ ] **T13: Swarm orchestrator**
  - Create `backend/agents/orchestrator.py` (see SYSTEM_DESIGN.md §3.1)
  - Two-tier execution: Exa first (fast), then Browser Use agents in parallel
  - Stream results to Convex as they arrive (don't wait for all agents)
  - 180-second timeout per agent
  - **Acceptance:** Trigger research → Convex shows data arriving incrementally from multiple sources

---

### PHASE 4: Frontend Magic (Hours 14-18)

- [ ] **T14: Corkboard canvas**
  - Create `components/Corkboard.tsx` (see DESIGN_HANDOFF.md §6)
  - Cork texture background (repeating image)
  - Mouse drag to pan, scroll to zoom
  - CSS transform on container div
  - **Acceptance:** Cork texture visible, can pan and zoom smoothly

- [ ] **T15: PersonCard component**
  - Create `components/PersonCard.tsx` (see DESIGN_HANDOFF.md §4.1)
  - Paper texture, pushpin, slight rotation
  - Photo thumbnail, name, title, status badge
  - Spawn animation with Framer Motion (see §5.1)
  - **Acceptance:** Cards appear on board with spring animation

- [ ] **T16: Real-time card updates**
  - Connect PersonCard to Convex `useQuery`
  - Cards update live as backend writes new data
  - Typewriter text animation for new data arriving
  - Status badge transitions (pending → researching → complete)
  - **Acceptance:** Backend mutation → card visibly updates on screen within 1 second

- [ ] **T17: ConnectionLine component**
  - Create `components/ConnectionLine.tsx` (see DESIGN_HANDOFF.md §4.2)
  - SVG overlay on corkboard
  - Dashed red line with glow
  - Draw animation (stroke-dashoffset)
  - Midpoint label
  - **Acceptance:** String draws itself between two connected cards

- [ ] **T18: DossierView panel**
  - Create `components/DossierView.tsx` (see DESIGN_HANDOFF.md §4.3)
  - Slide-in from right on card click
  - All dossier fields: work history, education, social, conversation hooks, risk flags
  - Scrollable content area
  - **Acceptance:** Click card → panel slides in with full dossier data

- [ ] **T19: LiveFeed sidebar**
  - Create `components/LiveFeed.tsx` (see DESIGN_HANDOFF.md §4.4)
  - Real-time event stream from Convex
  - New events slide in from top
  - Click event → scroll to related card on board
  - **Acceptance:** Backend activity shows up as live feed items

---

### PHASE 5: Synthesis + Polish (Hours 18-22)

- [ ] **T20: Report synthesizer**
  - Create `backend/synthesis/synthesizer.py` (see SYSTEM_DESIGN.md §4)
  - Aggregate all intel fragments for a person
  - Gemini 2.0 Flash generates: summary, conversation hooks, risk flags
  - Connection detection between people
  - Write final dossier to Convex
  - **Acceptance:** Person with multiple intel fragments → coherent dossier with hooks

- [ ] **T21: TopBar + StatusBar**
  - Create `components/TopBar.tsx` and `components/StatusBar.tsx`
  - JARVIS logo, agent status indicators, military clock
  - Bottom bar with system status counts
  - **Acceptance:** UI chrome looks polished and shows live status

- [ ] **T22: Laminar observability**
  - Install laminar SDK: `pip install lmnr`
  - Add `@observe()` decorators to all agent functions
  - Verify traces appear in Laminar dashboard
  - **Acceptance:** Full agent trace visible in Laminar for one end-to-end run

- [ ] **T23: "CLASSIFIED" stamp + polish**
  - ClassifiedStamp component with spring animation
  - Appears when dossier status → complete
  - Sound effects (optional): shutter, paper, typewriter
  - **Acceptance:** Completed dossier gets a dramatic stamp animation

---

### PHASE 5B: Ambient Intelligence + OSINT Depth (Hours 20-22)

- [ ] **T28: WiFi probe sniffer**
  - Create `backend/ambient/wifi_sniffer.py` (see SYSTEM_DESIGN.md §9.2)
  - Raspberry Pi 4 + Alfa AWUS036ACH in monitor mode
  - tshark captures probe requests → extract MAC + SSID
  - WiGLE API enriches SSID → GPS location (workplace/school inference)
  - **Acceptance:** Running at venue, capturing SSIDs from nearby devices

- [ ] **T29: BLE device scanner**
  - Create `backend/ambient/ble_scanner.py` (see SYSTEM_DESIGN.md §9.3)
  - Uses `bleak` library for async BLE scanning
  - Extract device names ("John's AirPods") → owner name parsing
  - **Acceptance:** Returns list of nearby BLE devices with inferred owner names

- [ ] **T30: FEC donation search agent**
  - Create `backend/agents/public_records/fec_agent.py` (see SYSTEM_DESIGN.md §10.4)
  - FEC API (free key) → search by name → political donations since 1977
  - **Acceptance:** Name search returns donation history with amounts and committees

- [ ] **T31: Public records Browser Use agents**
  - Create `backend/agents/public_records/people_search.py`
  - Browser Use agent for FastPeopleSearch / TruePeopleSearch
  - Extract: address, phone, relatives, associates
  - Fire in parallel during Tier 2 enrichment
  - **Acceptance:** Given a name → returns address + phone + associates

- [ ] **T32: OSINT username sweep (Sherlock + Maigret)**
  - Create `backend/agents/osint/username_sweep.py`
  - Run Sherlock (400+ sites, ~30s) and Maigret (2500+ sites, ~60s) in parallel
  - Parse results → list of confirmed accounts with URLs
  - **Acceptance:** Username → returns 20+ confirmed accounts across platforms

- [ ] **T33: Email intelligence (Holehe + HIBP)**
  - Create `backend/agents/osint/email_intel.py`
  - Holehe checks 120+ sites for email registration
  - HIBP checks breach count (ethical: count only, no data)
  - **Acceptance:** Email → list of registered services + breach count

- [ ] **T34: Live camera feed widget**
  - Create `backend/ambient/cameras/caltrans.py` + `nyc.py` (see SYSTEM_DESIGN.md §11)
  - Pull nearby camera feeds (Caltrans for SF, NYCTMC for NYC)
  - Frontend mini-map component showing live feeds on corkboard
  - **Acceptance:** Corkboard shows 2-3 live camera thumbnails refreshing every 15s

---

### PHASE 6: Demo Prep (Hours 22-24)

- [ ] **T24: Pre-seed demo data**
  - Create `scripts/seed_demo.py`
  - Pre-cache 2-3 complete dossiers with all fields populated
  - Ensure they appear on corkboard with connections on app load
  - **Acceptance:** App loads with 2-3 fully populated cards + connections

- [ ] **T25: Record backup video**
  - Screen record a full demo flow (capture → identify → research → dossier)
  - Edit with cuts for slow parts (PimEyes, Browser Use agent wait times)
  - Keep under 3 minutes
  - **Acceptance:** Video exists and plays smoothly

- [ ] **T26: Practice demo script**
  - Follow the 3-minute demo script from TECH_DOC.md §6
  - Time each section
  - Identify and fix any dead spots
  - **Acceptance:** Can deliver full demo in under 3 minutes without dead air

- [ ] **T27: Apply to manual prize tracks**
  - Submit for: Most Hardcore Infra, Best Design, Best Use of Real-Time Data
  - Check hackathon platform for submission deadlines
  - **Acceptance:** All 3 manual track applications submitted

---

## Quick Reference: Doc Locations
| Doc | What's in it |
|-----|-------------|
| `PRD.md` | Product requirements, judging alignment, features, risks |
| `ARCHITECTURE.md` | System architecture, data flow, component deep dives, API contracts |
| `TECH_DOC.md` | Project structure, build plan phases, Convex schema, agent patterns, env vars, demo script |
| `SYSTEM_DESIGN.md` | **Full implementation code** for backend/agents/pipelines — copy-paste into files |
| `DESIGN_HANDOFF.md` | **Full visual spec** for frontend — colors, typography, layouts, animations, components |
| `CREDITS_CHECKLIST.md` | Sponsor credit claim checklist |
