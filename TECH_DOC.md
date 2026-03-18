# Technical Documentation: JARVIS
## Developer Onboarding & Implementation Guide

**Version:** 0.1 | **Date:** 2026-02-27

---

## 1. Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- Browser Use API key ($100 credits)
- PimEyes account(s)
- OpenAI API key
- Google Gemini API key
- Convex account
- MongoDB Atlas cluster
- Exa API key (via MCP)

### Project Structure
```
jarvis/
├── backend/                    # Python FastAPI
│   ├── main.py                # Entry point, FastAPI app
│   ├── capture/               # Photo capture & processing
│   │   ├── service.py         # Capture endpoint logic
│   │   └── glasses.py         # Meta glasses integration
│   ├── identification/        # PimEyes + Vision LLM
│   │   ├── pimeyes.py         # PimEyes client (multi-account)
│   │   ├── vision.py          # GPT-4o vision extraction
│   │   └── pool.py            # Account rotation pool
│   ├── agents/                # Browser Use agent swarm
│   │   ├── orchestrator.py    # Swarm coordinator
│   │   ├── linkedin.py        # LinkedIn research agent
│   │   ├── twitter.py         # X/Twitter research agent
│   │   ├── instagram.py       # Instagram research agent
│   │   ├── google.py          # Google search agent
│   │   └── base.py            # Base agent class
│   ├── synthesis/             # Report generation
│   │   ├── synthesizer.py     # LLM-powered report synthesis
│   │   └── prompts.py         # System prompts for synthesis
│   ├── enrichment/            # API-based enrichment
│   │   ├── exa_client.py      # Exa API integration
│   │   └── supermemory.py     # Supermemory integration
│   ├── db/                    # Database clients
│   │   ├── convex_client.py   # Convex mutations/queries
│   │   └── mongo_client.py    # MongoDB operations
│   ├── observability/         # Tracing & monitoring
│   │   └── laminar.py         # Laminar integration
│   ├── config.py              # Environment config
│   └── requirements.txt
│
├── frontend/                   # Next.js (Vercel)
│   ├── app/
│   │   ├── page.tsx           # Corkboard main view
│   │   ├── person/[id]/       # Dossier detail view
│   │   └── layout.tsx
│   ├── components/
│   │   ├── Corkboard.tsx      # Main corkboard canvas
│   │   ├── PersonCard.tsx     # Individual paper/card
│   │   ├── ConnectionLine.tsx # Red string between cards
│   │   ├── DossierView.tsx    # Zoomed dossier panel
│   │   ├── LiveFeed.tsx       # Activity stream
│   │   └── StatusBar.tsx      # System status
│   ├── convex/
│   │   ├── schema.ts          # Convex schema definition
│   │   ├── persons.ts         # Person queries/mutations
│   │   ├── intel.ts           # Intel fragment operations
│   │   └── connections.ts     # Connection operations
│   ├── lib/
│   │   └── animations.ts      # Framer Motion presets
│   ├── package.json
│   └── next.config.js
│
├── scripts/
│   ├── setup_credits.sh       # Claim all sponsor credits
│   └── seed_demo.py           # Pre-seed demo data
│
├── .env.example
├── PRD.md
├── ARCHITECTURE.md
└── README.md
```

## 2. Implementation Order (Build Plan)

This is the critical path. 24 hours. No detours.

### Phase 1: Foundation (Hours 0-4)
1. Set up Convex project with schema
2. Set up FastAPI skeleton with capture endpoint
3. Set up Next.js project with Vercel
4. Get Convex ↔ Frontend real-time working (proof of life)
5. Claim ALL sponsor credits

### Phase 2: Identification Pipeline (Hours 4-8)
6. PimEyes integration with account pooling
7. GPT-4o Vision for name/URL extraction
8. End-to-end: photo → PimEyes → initial report → Convex → frontend shows card

### Phase 3: Agent Swarm (Hours 8-14)
9. Base Browser Use agent class
10. LinkedIn agent
11. X/Twitter agent
12. Google search agent
13. Orchestrator: parallel execution + streaming results to Convex
14. Exa API enrichment (parallel to browser agents)

### Phase 4: Frontend Magic (Hours 14-18)
15. Corkboard UI with cork texture, pins, papers
16. Spawn animation (papers slide in, pin, bounce)
17. Connection strings (red lines between related people)
18. Click-to-zoom dossier view
19. Live feed sidebar

### Phase 5: Synthesis + Polish (Hours 18-22)
20. Report synthesizer (LLM aggregation of all sources)
21. Confidence scoring
22. Laminar tracing for accuracy verification
23. Telegram/notification integration for glasses
24. Meta glasses → capture pipeline testing

### Phase 6: Demo Prep (Hours 22-24)
25. Record backup video
26. Pre-cache 2-3 people for warm demo
27. Practice 3-minute pitch
28. Apply to manual prize tracks (Hardcore Infra, Best Design, Best Real-Time Data)

## 3. Convex Schema

```typescript
// convex/schema.ts
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  captures: defineTable({
    imageUrl: v.string(),
    timestamp: v.number(),
    source: v.string(),
    status: v.union(
      v.literal("pending"),
      v.literal("identifying"),
      v.literal("identified"),
      v.literal("failed")
    ),
    personId: v.optional(v.id("persons")),
  }),

  persons: defineTable({
    name: v.string(),
    photoUrl: v.string(),
    confidence: v.number(),
    status: v.union(
      v.literal("identified"),
      v.literal("researching"),
      v.literal("synthesizing"),
      v.literal("complete")
    ),
    boardPosition: v.object({ x: v.number(), y: v.number() }),
    dossier: v.optional(v.object({
      summary: v.string(),
      title: v.optional(v.string()),
      company: v.optional(v.string()),
      workHistory: v.array(v.object({
        role: v.string(),
        company: v.string(),
        period: v.optional(v.string()),
      })),
      education: v.array(v.object({
        school: v.string(),
        degree: v.optional(v.string()),
      })),
      socialProfiles: v.object({
        linkedin: v.optional(v.string()),
        twitter: v.optional(v.string()),
        instagram: v.optional(v.string()),
        github: v.optional(v.string()),
        website: v.optional(v.string()),
      }),
      notableActivity: v.array(v.string()),
      conversationHooks: v.array(v.string()),
      riskFlags: v.array(v.string()),
    })),
    createdAt: v.number(),
    updatedAt: v.number(),
  }),

  intelFragments: defineTable({
    personId: v.id("persons"),
    source: v.string(),
    dataType: v.string(),
    content: v.string(),
    verified: v.boolean(),
    timestamp: v.number(),
  }).index("by_person", ["personId"]),

  connections: defineTable({
    personAId: v.id("persons"),
    personBId: v.id("persons"),
    relationshipType: v.string(),
    description: v.string(),
  }).index("by_person_a", ["personAId"])
    .index("by_person_b", ["personBId"]),
});
```

## 4. Browser Use Agent Pattern

```python
# backend/agents/base.py
from browser_use import Agent, Browser, BrowserConfig
from abc import ABC, abstractmethod

class ResearchAgent(ABC):
    """Base class for all research agents."""

    def __init__(self, person_name: str, person_context: dict):
        self.person_name = person_name
        self.context = person_context
        self.results = []

    @abstractmethod
    def get_task_prompt(self) -> str:
        """Return the task description for Browser Use."""
        pass

    @abstractmethod
    def get_target_url(self) -> str:
        """Return the starting URL for this agent."""
        pass

    async def run(self) -> dict:
        """Execute the research agent."""
        browser = Browser(config=BrowserConfig(headless=True))
        agent = Agent(
            task=self.get_task_prompt(),
            llm=self.get_llm(),
            browser=browser,
        )
        result = await agent.run()
        await browser.close()
        return self.parse_result(result)

    @abstractmethod
    def parse_result(self, raw_result) -> dict:
        """Parse Browser Use result into structured data."""
        pass


# backend/agents/linkedin.py
class LinkedInAgent(ResearchAgent):

    def get_task_prompt(self) -> str:
        return f"""
        Research {self.person_name} on LinkedIn.

        1. Go to linkedin.com/search and search for "{self.person_name}"
        2. If we have context clues: {self.context.get('company', '')},
           {self.context.get('location', '')} — use them to find the right person.
        3. Click on the most likely profile.
        4. Extract: full name, headline, current company, current title,
           location, about section, experience (last 3 roles), education,
           skills (top 5), recent posts (last 3).
        5. Return all extracted data as structured JSON.
        """

    def get_target_url(self) -> str:
        return "https://www.linkedin.com/search/results/people/"


# backend/agents/orchestrator.py
import asyncio
from typing import List
from .linkedin import LinkedInAgent
from .twitter import TwitterAgent
from .instagram import InstagramAgent
from .google import GoogleAgent

class SwarmOrchestrator:
    """Coordinates parallel research agents for a single person."""

    def __init__(self, person_id: str, initial_report: dict):
        self.person_id = person_id
        self.report = initial_report
        self.agents: List[ResearchAgent] = []

    def create_agents(self):
        name = self.report["name"]
        context = self.report.get("context", {})

        self.agents = [
            LinkedInAgent(name, context),
            TwitterAgent(name, context),
            InstagramAgent(name, context),
            GoogleAgent(name, context),
        ]

    async def execute(self, on_result_callback=None):
        """Run all agents in parallel, streaming results."""
        self.create_agents()

        async def run_with_callback(agent):
            try:
                result = await asyncio.wait_for(agent.run(), timeout=180)
                if on_result_callback:
                    await on_result_callback(self.person_id, result)
                return result
            except asyncio.TimeoutError:
                return {"source": agent.__class__.__name__, "error": "timeout"}
            except Exception as e:
                return {"source": agent.__class__.__name__, "error": str(e)}

        results = await asyncio.gather(
            *[run_with_callback(agent) for agent in self.agents]
        )
        return results
```

## 5. Environment Variables

```bash
# .env.example

# Browser Use
BROWSER_USE_API_KEY=

# PimEyes (multiple accounts)
PIMEYES_ACCOUNT_1_EMAIL=
PIMEYES_ACCOUNT_1_PASSWORD=
PIMEYES_ACCOUNT_2_EMAIL=
PIMEYES_ACCOUNT_2_PASSWORD=
PIMEYES_ACCOUNT_3_EMAIL=
PIMEYES_ACCOUNT_3_PASSWORD=

# LLMs
OPENAI_API_KEY=
GOOGLE_GEMINI_API_KEY=

# Databases
CONVEX_URL=
CONVEX_DEPLOY_KEY=
MONGODB_URI=

# Research
EXA_API_KEY=

# Observability
LAMINAR_API_KEY=
HUD_API_KEY=

# Notifications
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Memory
SUPERMEMORY_API_KEY=
```

## 6. Demo Script (3 minutes)

```
[0:00-0:15] HOOK
"What if you could walk into any room and instantly know everything
about everyone in it?"

[0:15-0:30] SHOW THE GLASSES
Put on Meta glasses. "These glasses are running JARVIS."

[0:30-1:30] LIVE DEMO — CAPTURE
Look at person 1. "I just looked at them. Watch what happens."
Cut to corkboard. Paper spawns in. Name appears. Data starts streaming.
"In real-time, JARVIS deployed 6 browser agents to research this
person across LinkedIn, X, Instagram, and the open web."

[1:30-2:15] LIVE DEMO — DEPTH
Click on the dossier. Show the detail. "Here's their full profile —
work history, education, social activity, and even conversation hooks.
JARVIS tells me to ask them about their recent Series B."
Look at person 2. Second paper spawns. Connection string draws.
"And it found they used to work together at Google."

[2:15-2:45] TECHNICAL DEPTH
"Under the hood: Browser Use agents running in parallel, PimEyes for
facial recognition, Exa for structured research, Convex for real-time
streaming, Laminar for accuracy verification. All orchestrated by a
Python swarm coordinator."

[2:45-3:00] CLOSE
"JARVIS turns any room into an intelligence briefing.
The future of networking isn't small talk — it's information."

[3:00-4:00] Q&A
```
