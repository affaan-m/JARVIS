# SPECTER — Detailed System Design & Implementation Manual
## For Coding Agent Handoff

**Version:** 0.3 | **Date:** 2026-02-28 | **Status:** READY TO BUILD

---

## 0. Key Technical Decisions (LOCKED IN)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vision/OCR Model | **Gemini 2.0 Flash** | 25x cheaper than GPT-4o, 2x faster, excellent screenshot parsing |
| Synthesis LLM | **Gemini 2.0 Flash** | Same model, cheap enough for bulk synthesis |
| Glasses Streaming | **VisionClaw (fork)** | 1.4k★, Feb 2026, already solves Ray-Ban→cloud streaming + Gemini Live |
| Facial Recognition | **PimEyes via Browser Use + PicImageSearch fallback** | PimEyes for faces, PicImageSearch for multi-engine reverse search |
| Face Detection | **mediapipe + InsightFace/ArcFace embeddings** | mediapipe fast detect, ArcFace 512-dim embeddings for matching |
| Capture Device | **Meta Ray-Ban Gen 2 via VisionClaw** | VisionClaw handles streaming; phone camera fallback built-in |
| Capture Pipeline | **VisionClaw streaming → face detect → identify** | Fork VisionClaw, add face pipeline layer. NOT building from scratch. |
| LinkedIn Extraction | **Browser Use + Voyager API interception** | 2-5 sec/profile, fastest zero-cost option |
| X/Twitter Extraction | **Reverse GraphQL (twscrape)** | 2-5 sec/profile, free, actively maintained |
| Instagram Extraction | **Browser Use scrape public profiles** | 20-40 sec/profile, no API available |
| Fast Person Lookup | **Exa API** | 200ms person search, use as first-pass before browser agents |
| Real-time DB | **Convex** | Zero WebSocket boilerplate, real-time subscriptions |
| Persistent Storage | **MongoDB Atlas** | Free cluster, document-oriented |
| Agent Framework | **Browser Use SDK (Python)** | Hackathon sponsor, mandatory usage, good Python SDK |
| Frontend | **Next.js + Framer Motion + Tailwind** | Fast to build, great animations, Vercel deploy |
| Observability | **Laminar** | Agent tracing, accuracy verification |

---

## 1. CAPTURE SERVICE (Module: `backend/capture/`)

### 1.1 Overview
The capture service receives frames from Meta Ray-Ban glasses and feeds them into the identification pipeline. This is a **deterministic pipeline**, not an agentic system.

### 1.2 Data Flow
```
Meta Ray-Ban Gen 2
  │ (manual button press → 30-60s video)
  ▼
Meta AI App (phone)
  │ (video auto-syncs)
  ▼
Telegram Bot OR Direct Upload
  │ (user sends video/photo to bot, OR script polls phone storage)
  ▼
┌─────────────────────────────────────┐
│ capture_service.py                   │
│                                      │
│ 1. Receive video/image              │
│ 2. If video → ffmpeg extract frames │
│    ffmpeg -i input.mp4 -vf fps=1    │
│    -q:v 2 frame_%03d.jpg            │
│ 3. For each frame:                  │
│    a. Face detection (mediapipe)    │
│    b. If face found → crop face    │
│    c. Generate capture_id (uuid4)  │
│    d. Store raw in MongoDB GridFS  │
│    e. Create Convex capture record │
│       status: "pending"            │
│    f. Enqueue for identification   │
│ 4. Return capture_ids              │
└─────────────────────────────────────┘
```

### 1.3 Implementation Details

**File: `backend/capture/service.py`**
```python
import uuid
import asyncio
import subprocess
import tempfile
from pathlib import Path
from fastapi import UploadFile
import mediapipe as mp

class CaptureService:
    def __init__(self, convex_client, mongo_client):
        self.convex = convex_client
        self.mongo = mongo_client
        self.face_detector = mp.solutions.face_detection.FaceDetection(
            min_detection_confidence=0.7
        )

    async def process_upload(self, file: UploadFile) -> list[str]:
        """Process uploaded video or image. Returns list of capture_ids."""
        content = await file.read()

        if file.content_type.startswith("video/"):
            frames = await self._extract_frames(content)
        else:
            frames = [content]

        capture_ids = []
        for frame_bytes in frames:
            faces = self._detect_faces(frame_bytes)
            for face_crop in faces:
                capture_id = str(uuid.uuid4())
                # Store raw image
                await self.mongo.store_image(capture_id, face_crop)
                # Create Convex record
                await self.convex.mutation("captures:create", {
                    "captureId": capture_id,
                    "imageUrl": f"/api/images/{capture_id}",
                    "timestamp": time.time(),
                    "source": "meta_glasses",
                    "status": "pending"
                })
                capture_ids.append(capture_id)

        return capture_ids

    async def _extract_frames(self, video_bytes: bytes, fps: int = 1) -> list[bytes]:
        """Extract frames from video using ffmpeg."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.mp4"
            input_path.write_bytes(video_bytes)

            output_pattern = Path(tmpdir) / "frame_%03d.jpg"
            subprocess.run([
                "ffmpeg", "-i", str(input_path),
                "-vf", f"fps={fps}",
                "-q:v", "2",
                str(output_pattern)
            ], check=True, capture_output=True)

            frames = []
            for frame_path in sorted(Path(tmpdir).glob("frame_*.jpg")):
                frames.append(frame_path.read_bytes())
            return frames

    def _detect_faces(self, image_bytes: bytes) -> list[bytes]:
        """Detect and crop faces from image. Returns cropped face images."""
        # Convert bytes to numpy array via PIL
        # Use mediapipe face detection
        # Crop each detected face with padding
        # Return list of cropped face bytes
        ...
```

**File: `backend/capture/telegram_bot.py`**
```python
from telegram import Update
from telegram.ext import Application, MessageHandler, filters

class CaptureBot:
    """Telegram bot that receives photos/videos from Meta glasses."""

    def __init__(self, token: str, capture_service: CaptureService):
        self.app = Application.builder().token(token).build()
        self.capture_service = capture_service

        # Handle photos and videos
        self.app.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO,
            self.handle_media
        ))

    async def handle_media(self, update: Update, context):
        """Process incoming media from glasses."""
        if update.message.photo:
            file = await update.message.photo[-1].get_file()
        elif update.message.video:
            file = await update.message.video.get_file()

        content = await file.download_as_bytearray()
        capture_ids = await self.capture_service.process_upload(content)

        await update.message.reply_text(
            f"Processing {len(capture_ids)} face(s)..."
        )
```

### 1.4 Face Detection: mediapipe vs alternatives

| Option | Speed | Accuracy | Install |
|--------|-------|----------|---------|
| **mediapipe** (USE THIS) | 5-10ms/frame | 95%+ | `pip install mediapipe` |
| dlib | 50-100ms/frame | 98% | Complex C++ deps |
| MTCNN | 100ms/frame | 97% | `pip install mtcnn` |
| OpenCV Haar | 2-5ms/frame | 80% | Built-in |

**Decision: mediapipe.** Fast, accurate, zero compilation hassles.

---

## 2. IDENTIFICATION PIPELINE (Module: `backend/identification/`)

### 2.1 Overview
Takes a cropped face image, runs it through PimEyes (via Browser Use), and uses Gemini 2.0 Flash to extract identity information from the results page.

### 2.2 Data Flow
```
Cropped Face Image
  │
  ▼
┌──────────────────────────────────────────────┐
│ PimEyes Search (via Browser Use)              │
│                                               │
│ 1. Select PimEyes account from pool          │
│ 2. Launch Browser Use agent:                 │
│    a. Navigate to pimeyes.com                │
│    b. Upload face image                      │
│    c. Wait for results page                  │
│    d. Screenshot results                     │
│ 3. Parse with Gemini 2.0 Flash:             │
│    a. Send screenshot to Gemini              │
│    b. Extract: names, URLs, thumbnails       │
│    c. Structured JSON output                 │
│ 4. Update Convex:                            │
│    capture.status → "identified"             │
│    Create person record with initial data    │
│ 5. Trigger agent swarm for deep research     │
└──────────────────────────────────────────────┘
```

### 2.3 Implementation Details

**File: `backend/identification/pimeyes.py`**
```python
import asyncio
import base64
from browser_use import Agent, Browser, BrowserConfig
import google.generativeai as genai

class PimEyesSearcher:
    """Searches PimEyes for face matches using Browser Use."""

    def __init__(self, accounts: list[dict], gemini_api_key: str):
        self.accounts = accounts  # [{email, password}, ...]
        self.current_idx = 0
        self.lock = asyncio.Lock()
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    def _rotate_account(self) -> dict:
        """Round-robin account selection."""
        async with self.lock:
            account = self.accounts[self.current_idx]
            self.current_idx = (self.current_idx + 1) % len(self.accounts)
            return account

    async def search(self, face_image_bytes: bytes) -> dict:
        """Run PimEyes search and extract identity info."""
        account = self._rotate_account()

        # Browser Use agent to navigate PimEyes
        browser = Browser(config=BrowserConfig(headless=True))
        agent = Agent(
            task=f"""
            1. Go to https://pimeyes.com
            2. Log in with email: {account['email']}, password: {account['password']}
            3. Upload the provided face image for search
            4. Wait for results to load (up to 30 seconds)
            5. Take a screenshot of the full results page
            6. Return the screenshot
            """,
            llm="gemini-2.0-flash",
            browser=browser,
        )

        result = await agent.run()
        screenshot = result.screenshot()  # Get results page screenshot
        await browser.close()

        # Parse screenshot with Gemini
        identity = await self._parse_results(screenshot)
        return identity

    async def _parse_results(self, screenshot_bytes: bytes) -> dict:
        """Use Gemini 2.0 Flash to extract identity from PimEyes results."""
        image_b64 = base64.b64encode(screenshot_bytes).decode()

        response = self.model.generate_content([
            {
                "mime_type": "image/png",
                "data": image_b64
            },
            """Analyze this PimEyes search results page. Extract:
            1. The most likely name of the person
            2. All URLs shown in results (social media, websites, articles)
            3. Context clues (company, title, location) visible in results
            4. Confidence level (high/medium/low) based on match quality

            Return ONLY valid JSON:
            {
                "name": "string or null",
                "urls": ["url1", "url2"],
                "context": {"company": "", "title": "", "location": ""},
                "confidence": "high|medium|low",
                "match_count": number
            }"""
        ])

        return json.loads(response.text)
```

**File: `backend/identification/pool.py`**
```python
import asyncio
import time

class AccountPool:
    """Manages PimEyes account rotation with rate limiting."""

    def __init__(self, accounts: list[dict]):
        self.accounts = [
            {**acc, "last_used": 0, "blocked": False}
            for acc in accounts
        ]
        self.lock = asyncio.Lock()
        self.MIN_INTERVAL = 30  # seconds between uses per account

    async def get_account(self) -> dict:
        """Get next available account respecting rate limits."""
        async with self.lock:
            now = time.time()
            for acc in self.accounts:
                if not acc["blocked"] and (now - acc["last_used"]) > self.MIN_INTERVAL:
                    acc["last_used"] = now
                    return acc

            # All accounts busy — wait for shortest cooldown
            wait_times = [
                self.MIN_INTERVAL - (now - acc["last_used"])
                for acc in self.accounts if not acc["blocked"]
            ]
            if wait_times:
                await asyncio.sleep(min(wait_times))
                return await self.get_account()

            raise RuntimeError("All PimEyes accounts blocked")

    def mark_blocked(self, email: str):
        """Mark account as blocked by PimEyes."""
        for acc in self.accounts:
            if acc["email"] == email:
                acc["blocked"] = True
```

### 2.4 Fallback: Google Reverse Image Search
If PimEyes fails or gets blocked, fall back to Google Lens via Browser Use:
```python
async def google_reverse_search(face_image_bytes: bytes) -> dict:
    """Fallback: use Google Lens for face identification."""
    agent = Agent(
        task="""
        1. Go to https://lens.google.com
        2. Upload the provided face image
        3. Look for matches — especially social media profiles
        4. Screenshot the results page
        """,
        llm="gemini-2.0-flash",
        browser=Browser(config=BrowserConfig(headless=True)),
    )
    result = await agent.run()
    # Parse with Gemini same as PimEyes
    ...
```

---

## 3. AGENT SWARM ORCHESTRATOR (Module: `backend/agents/`)

### 3.1 Architecture: Two-Tier Research

**Tier 1: Fast API Enrichment (< 1 second)**
- Exa API: Person search → LinkedIn URL, company, title
- This runs FIRST and provides context to Tier 2

**Tier 2: Deep Browser Research (10-60 seconds)**
- Browser Use agents run IN PARALLEL across platforms
- Each agent gets Tier 1 context (name, likely LinkedIn URL, company)
- Results stream to Convex as they arrive

```
Identity from PimEyes
  │
  ├──▶ Tier 1: Exa API (200ms)
  │       │
  │       ├── LinkedIn URL
  │       ├── Company, Title
  │       └── Web mentions
  │
  │    (context passed to Tier 2)
  │
  └──▶ Tier 2: Browser Use Agents (parallel, 10-60s)
          │
          ├── LinkedIn Agent (Voyager API intercept, 2-5s)
          ├── Twitter Agent (GraphQL reverse-eng, 2-5s)
          ├── Instagram Agent (Browser scrape, 20-40s)
          └── Google Agent (Exa deep search, 1-2s)

  Each agent → Convex intel_fragments (streaming)
  All complete → Synthesizer → Convex person.dossier
```

### 3.2 Implementation

**File: `backend/agents/orchestrator.py`**
```python
import asyncio
from typing import Callable, Optional
from .linkedin_agent import LinkedInAgent
from .twitter_agent import TwitterAgent
from .instagram_agent import InstagramAgent
from .exa_agent import ExaEnrichment

class SwarmOrchestrator:
    """Coordinates two-tier research for a single person."""

    TIMEOUT_SECONDS = 180  # 3 minutes max per person

    def __init__(
        self,
        person_id: str,
        identity: dict,  # from PimEyes
        convex_client,
        exa_client,
        browser_use_api_key: str,
    ):
        self.person_id = person_id
        self.identity = identity
        self.convex = convex_client
        self.exa = exa_client
        self.bu_key = browser_use_api_key

    async def execute(self) -> dict:
        """Run full two-tier research pipeline."""

        # Update status
        await self.convex.mutation("persons:updateStatus", {
            "personId": self.person_id,
            "status": "researching"
        })

        # TIER 1: Fast API enrichment (< 1 second)
        exa_context = await ExaEnrichment(self.exa).search_person(
            name=self.identity.get("name"),
            context=self.identity.get("context", {})
        )

        # Stream Tier 1 results immediately
        await self._store_fragment("exa", "enrichment", exa_context)

        # TIER 2: Deep browser research (parallel)
        agents = self._create_agents(exa_context)

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[self._run_agent(agent) for agent in agents],
                    return_exceptions=True
                ),
                timeout=self.TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            results = []  # Partial results already streamed

        # Trigger synthesis
        return await self._synthesize()

    def _create_agents(self, exa_context: dict) -> list:
        """Create research agents with Tier 1 context."""
        name = self.identity.get("name", "")
        context = {
            **self.identity.get("context", {}),
            **exa_context,
        }

        agents = []

        # LinkedIn — only if we have a URL or name
        if exa_context.get("linkedin_url") or name:
            agents.append(LinkedInAgent(
                name=name,
                linkedin_url=exa_context.get("linkedin_url"),
                context=context,
                api_key=self.bu_key,
            ))

        # Twitter — search by name
        if name:
            agents.append(TwitterAgent(
                name=name,
                context=context,
            ))

        # Instagram — only if public profile likely
        if name:
            agents.append(InstagramAgent(
                name=name,
                context=context,
                api_key=self.bu_key,
            ))

        return agents

    async def _run_agent(self, agent) -> dict:
        """Run single agent and stream results to Convex."""
        try:
            result = await agent.run()
            await self._store_fragment(
                source=agent.SOURCE_NAME,
                data_type="profile",
                content=result
            )
            return result
        except Exception as e:
            await self._store_fragment(
                source=agent.SOURCE_NAME,
                data_type="error",
                content={"error": str(e)}
            )
            return {"error": str(e)}

    async def _store_fragment(self, source: str, data_type: str, content: dict):
        """Stream a single intel fragment to Convex."""
        await self.convex.mutation("intelFragments:create", {
            "personId": self.person_id,
            "source": source,
            "dataType": data_type,
            "content": json.dumps(content),
            "verified": False,
            "timestamp": time.time(),
        })

    async def _synthesize(self) -> dict:
        """Trigger report synthesis from all fragments."""
        from ..synthesis.synthesizer import ReportSynthesizer
        synthesizer = ReportSynthesizer(self.convex)
        return await synthesizer.synthesize(self.person_id)
```

**File: `backend/agents/linkedin_agent.py`**
```python
from browser_use import Agent, Browser, BrowserConfig

class LinkedInAgent:
    """Extracts LinkedIn profile data using Browser Use."""

    SOURCE_NAME = "linkedin"

    def __init__(self, name: str, linkedin_url: str = None, context: dict = None, api_key: str = None):
        self.name = name
        self.linkedin_url = linkedin_url
        self.context = context or {}
        self.api_key = api_key

    async def run(self) -> dict:
        """Navigate LinkedIn and extract profile data."""

        if self.linkedin_url:
            task = f"""
            1. Go to {self.linkedin_url}
            2. Extract all visible profile information:
               - Full name, headline, location
               - Current company and title
               - About/summary section
               - Experience (last 3 roles with companies and dates)
               - Education
               - Skills (top 5)
               - Number of connections/followers
               - Recent activity/posts (last 3 if visible)
            3. Return all data as structured JSON.
            """
        else:
            company = self.context.get("company", "")
            task = f"""
            1. Go to https://www.linkedin.com/search/results/people/?keywords={self.name}
            2. Look for someone named "{self.name}"
               {f'who works at {company}' if company else ''}
            3. Click on the most likely profile match
            4. Extract all visible profile information:
               - Full name, headline, location
               - Current company and title
               - About/summary section
               - Experience (last 3 roles)
               - Education
               - Skills (top 5)
            5. Return all data as structured JSON.
            """

        browser = Browser(config=BrowserConfig(headless=True))
        agent = Agent(
            task=task,
            llm="gemini-2.0-flash",
            browser=browser,
        )

        result = await agent.run()
        await browser.close()

        return self._parse_result(result)

    def _parse_result(self, raw_result) -> dict:
        """Parse Browser Use result into structured profile data."""
        # Extract the final result text from the agent
        # Parse JSON from the agent's response
        return {
            "source": "linkedin",
            "profile_url": self.linkedin_url,
            "data": raw_result.final_result(),
        }
```

**File: `backend/agents/twitter_agent.py`**
```python
import asyncio

class TwitterAgent:
    """Extracts X/Twitter data using reverse-engineered GraphQL."""

    SOURCE_NAME = "twitter"

    def __init__(self, name: str, context: dict = None):
        self.name = name
        self.context = context or {}

    async def run(self) -> dict:
        """Search and extract Twitter profile data."""
        try:
            # Try twscrape first (reverse-engineered GraphQL)
            return await self._twscrape_search()
        except Exception:
            # Fallback to Browser Use
            return await self._browser_search()

    async def _twscrape_search(self) -> dict:
        """Use twscrape for fast Twitter data extraction."""
        from twscrape import API

        api = API()
        # Search for user by name
        users = await api.search_users(self.name, limit=5)

        if not users:
            return {"source": "twitter", "data": None}

        # Pick best match (heuristic: verified, follower count, name match)
        best = users[0]

        # Get recent tweets
        tweets = await api.user_tweets(best.id, limit=5)

        return {
            "source": "twitter",
            "data": {
                "username": best.username,
                "display_name": best.displayname,
                "bio": best.rawDescription,
                "followers": best.followersCount,
                "following": best.friendsCount,
                "verified": best.verified,
                "location": best.location,
                "website": best.url,
                "recent_tweets": [
                    {"text": t.rawContent, "likes": t.likeCount, "date": str(t.date)}
                    for t in tweets[:5]
                ]
            }
        }

    async def _browser_search(self) -> dict:
        """Fallback: Browser Use to scrape X profile."""
        from browser_use import Agent, Browser, BrowserConfig

        agent = Agent(
            task=f"""
            1. Go to https://x.com/search?q={self.name}&f=user
            2. Find the most relevant profile for "{self.name}"
            3. Click on the profile
            4. Extract: username, bio, follower count, recent tweets (last 3)
            5. Return as JSON
            """,
            llm="gemini-2.0-flash",
            browser=Browser(config=BrowserConfig(headless=True)),
        )
        result = await agent.run()
        return {"source": "twitter", "data": result.final_result()}
```

**File: `backend/agents/exa_agent.py`**
```python
from exa_py import Exa

class ExaEnrichment:
    """Fast person lookup using Exa search API (~200ms)."""

    def __init__(self, exa_client: Exa):
        self.exa = exa_client

    async def search_person(self, name: str, context: dict = None) -> dict:
        """Search for a person using Exa. Returns enrichment data."""
        context = context or {}
        company = context.get("company", "")

        # Build search query
        query = f"{name}"
        if company:
            query += f" {company}"
        query += " LinkedIn profile"

        results = self.exa.search_and_contents(
            query=query,
            type="neural",
            num_results=5,
            text=True,
            highlights=True,
        )

        # Extract LinkedIn URL if found
        linkedin_url = None
        for r in results.results:
            if "linkedin.com/in/" in r.url:
                linkedin_url = r.url
                break

        # Extract key info from results
        return {
            "linkedin_url": linkedin_url,
            "web_mentions": [
                {"title": r.title, "url": r.url, "snippet": r.text[:200]}
                for r in results.results[:5]
            ],
            "search_query": query,
        }
```

---

## 4. REPORT SYNTHESIZER (Module: `backend/synthesis/`)

### 4.1 Overview
Aggregates all intel fragments for a person into a coherent dossier using Gemini 2.0 Flash.

**File: `backend/synthesis/synthesizer.py`**
```python
import json
import google.generativeai as genai

class ReportSynthesizer:
    """Synthesizes all intel fragments into a coherent dossier."""

    def __init__(self, convex_client, gemini_api_key: str):
        self.convex = convex_client
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")

    async def synthesize(self, person_id: str) -> dict:
        """Aggregate all fragments and generate structured dossier."""

        # Get all fragments for this person
        fragments = await self.convex.query("intelFragments:byPerson", {
            "personId": person_id
        })

        # Build context from fragments
        fragment_text = "\n\n".join([
            f"Source: {f['source']} ({f['dataType']})\n{f['content']}"
            for f in fragments
        ])

        # Synthesize with Gemini
        response = self.model.generate_content(f"""
You are an intelligence analyst. Given the following raw data fragments about a person,
synthesize them into a structured dossier. Cross-reference for accuracy. Flag contradictions.

RAW DATA:
{fragment_text}

Output ONLY valid JSON matching this schema:
{{
    "name": "Full Name",
    "title": "Current Title",
    "company": "Current Company",
    "summary": "2-3 sentence overview of who this person is",
    "workHistory": [
        {{"role": "Title", "company": "Company", "period": "2020-present"}}
    ],
    "education": [
        {{"school": "School Name", "degree": "Degree"}}
    ],
    "socialProfiles": {{
        "linkedin": "url or null",
        "twitter": "url or null",
        "instagram": "url or null",
        "github": "url or null",
        "website": "url or null"
    }},
    "notableActivity": ["Recent notable things they've done/posted"],
    "conversationHooks": [
        "Specific things you could bring up in conversation with this person"
    ],
    "riskFlags": ["Any concerning or contradictory information"],
    "confidence": 0.0-1.0
}}
""")

        dossier = json.loads(response.text)

        # Update person record in Convex
        await self.convex.mutation("persons:updateDossier", {
            "personId": person_id,
            "dossier": dossier,
            "status": "complete"
        })

        # Detect connections to other people
        await self._detect_connections(person_id, dossier)

        return dossier

    async def _detect_connections(self, person_id: str, dossier: dict):
        """Find connections between this person and others on the board."""
        all_persons = await self.convex.query("persons:list")

        for other in all_persons:
            if other["_id"] == person_id:
                continue
            if not other.get("dossier"):
                continue

            # Check for shared companies, schools, mutual follows
            shared = self._find_shared(dossier, other["dossier"])
            if shared:
                await self.convex.mutation("connections:create", {
                    "personAId": person_id,
                    "personBId": other["_id"],
                    "relationshipType": shared["type"],
                    "description": shared["description"],
                })

    def _find_shared(self, dossier_a: dict, dossier_b: dict) -> dict | None:
        """Find shared connections between two people."""
        # Check shared companies
        companies_a = {w["company"].lower() for w in dossier_a.get("workHistory", [])}
        companies_b = {w["company"].lower() for w in dossier_b.get("workHistory", [])}
        shared_companies = companies_a & companies_b

        if shared_companies:
            return {
                "type": "coworker",
                "description": f"Both worked at {', '.join(shared_companies)}"
            }

        # Check shared schools
        schools_a = {e["school"].lower() for e in dossier_a.get("education", [])}
        schools_b = {e["school"].lower() for e in dossier_b.get("education", [])}
        shared_schools = schools_a & schools_b

        if shared_schools:
            return {
                "type": "classmate",
                "description": f"Both attended {', '.join(shared_schools)}"
            }

        return None
```

---

## 5. FASTAPI MAIN APP (Module: `backend/main.py`)

```python
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import asyncio

app = FastAPI(title="SPECTER API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Hackathon mode
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services (from config)
capture_service = CaptureService(convex, mongo)
pimeyes_searcher = PimEyesSearcher(accounts, gemini_key)
orchestrators = {}  # person_id -> SwarmOrchestrator

@app.post("/api/capture")
async def capture(file: UploadFile = File(...)):
    """Receive photo/video, detect faces, start identification."""
    capture_ids = await capture_service.process_upload(file)

    # Process each face asynchronously
    for capture_id in capture_ids:
        asyncio.create_task(process_face(capture_id))

    return {"capture_ids": capture_ids, "status": "processing"}

async def process_face(capture_id: str):
    """Full pipeline: identify → research → synthesize."""
    # Get image from MongoDB
    image_bytes = await mongo.get_image(capture_id)

    # Step 1: PimEyes identification
    identity = await pimeyes_searcher.search(image_bytes)

    # Step 2: Create person in Convex
    person_id = await convex.mutation("persons:create", {
        "name": identity.get("name", "Unknown"),
        "photoUrl": f"/api/images/{capture_id}",
        "confidence": 0.8 if identity.get("confidence") == "high" else 0.5,
        "status": "identified",
        "boardPosition": {"x": random.randint(100, 900), "y": random.randint(100, 600)},
        "createdAt": time.time(),
        "updatedAt": time.time(),
    })

    # Update capture with person link
    await convex.mutation("captures:linkPerson", {
        "captureId": capture_id,
        "personId": person_id,
    })

    # Step 3: Launch agent swarm
    orchestrator = SwarmOrchestrator(
        person_id=person_id,
        identity=identity,
        convex_client=convex,
        exa_client=exa,
        browser_use_api_key=config.BROWSER_USE_API_KEY,
    )
    orchestrators[person_id] = orchestrator
    await orchestrator.execute()

@app.get("/api/person/{person_id}")
async def get_person(person_id: str):
    """Get full person data."""
    return await convex.query("persons:get", {"personId": person_id})

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "specter"}
```

---

## 6. REQUIREMENTS & DEPENDENCIES

**File: `backend/requirements.txt`**
```
fastapi==0.115.0
uvicorn==0.30.0
python-telegram-bot==21.0
browser-use==0.2.0
google-generativeai==0.8.0
exa-py==1.0.0
mediapipe==0.10.14
pymongo==4.8.0
motor==3.5.0
convex==0.7.0
twscrape==0.12.0
laminar-ai==0.5.0
python-dotenv==1.0.0
Pillow==10.4.0
numpy==1.26.0
```

**File: `frontend/package.json`** (key deps)
```json
{
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "convex": "^1.14.0",
    "framer-motion": "^11.5.0",
    "tailwindcss": "^3.4.0"
  }
}
```

---

## 7. OBSERVABILITY WITH LAMINAR

**File: `backend/observability/laminar.py`**
```python
from lmnr import Laminar, observe

# Initialize at app startup
Laminar.initialize(project_api_key=config.LAMINAR_API_KEY)

@observe()
async def identify_person(image_bytes: bytes) -> dict:
    """Traced: PimEyes search + Gemini extraction."""
    ...

@observe()
async def synthesize_report(person_id: str) -> dict:
    """Traced: Report synthesis from all intel fragments."""
    ...

@observe()
async def agent_research(agent_name: str, person_name: str) -> dict:
    """Traced: Individual agent research run."""
    ...
```

Every LLM call and agent run gets traced in Laminar → visible in dashboard → verify accuracy during demo.

---

## 8. ENVIRONMENT CONFIGURATION

**File: `backend/config.py`**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Browser Use
    BROWSER_USE_API_KEY: str

    # PimEyes accounts (JSON array)
    PIMEYES_ACCOUNTS: str  # '[{"email":"a@b.com","password":"xxx"}]'

    # LLMs
    GOOGLE_GEMINI_API_KEY: str

    # Databases
    CONVEX_URL: str
    CONVEX_DEPLOY_KEY: str
    MONGODB_URI: str

    # Research
    EXA_API_KEY: str

    # Observability
    LAMINAR_API_KEY: str

    # Notifications
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    class Config:
        env_file = ".env"

config = Settings()
```

---

## 9. AMBIENT INTELLIGENCE LAYER (Module: `backend/ambient/`)

### 9.1 Overview
Beyond face-based identification, SPECTER collects passive signals from the physical environment to enrich profiles and demonstrate depth. This layer runs on commodity hardware ($100 total) deployed at the hackathon venue.

### 9.2 WiFi Probe Request Sniffing

**Hardware:** Raspberry Pi 4 (~$45) + Alfa AWUS036ACH (~$40) in monitor mode
**Alternative:** ESP32 Marauder (~$30) or Flipper Zero

**How it works:**
Devices constantly broadcast "probe requests" containing SSIDs of networks they've previously connected to. This reveals:
- Home/work WiFi names (e.g., "GoogleGuest" → works at Google, "MIT" → attended MIT)
- Hotel/airport WiFi history (travel patterns)
- Device manufacturer from MAC OUI prefix

**Implementation:**
```python
# backend/ambient/wifi_sniffer.py
# RESEARCH: tshark + scapy for probe capture, WiGLE API for SSID→GPS mapping
# DECISION: tshark CLI parsing — fastest, no Python overhead
# ALT: scapy (pure Python, slower but more flexible)

import subprocess
import asyncio
from typing import AsyncGenerator
from loguru import logger

async def capture_probes(interface: str = "wlan0mon") -> AsyncGenerator[dict, None]:
    """Stream WiFi probe requests from monitor-mode interface."""
    cmd = [
        "tshark", "-i", interface, "-l",
        "-Y", "wlan.fc.type_subtype == 0x04",
        "-T", "fields",
        "-e", "wlan.sa",              # Source MAC
        "-e", "wlan_mgt.ssid",        # Probed SSID
        "-e", "radiotap.dbm_antsignal" # Signal strength (proximity)
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    async for line in proc.stdout:
        parts = line.decode().strip().split("\t")
        if len(parts) >= 2:
            yield {
                "mac": parts[0],
                "ssid": parts[1] if parts[1] else None,
                "signal_dbm": int(parts[2]) if len(parts) > 2 and parts[2] else None,
                "oui_vendor": lookup_oui(parts[0][:8])
            }

async def enrich_ssid_location(ssid: str) -> dict | None:
    """Use WiGLE API to geolocate an SSID."""
    # WiGLE API: https://api.wigle.net/api/v2/network/search
    # Returns GPS coordinates where this SSID has been seen
    # Free tier: 100 queries/day
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.wigle.net/api/v2/network/search",
            params={"ssid": ssid},
            headers={"Authorization": f"Basic {config.WIGLE_API_KEY}"},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("results"):
                    r = data["results"][0]
                    return {"ssid": ssid, "lat": r["trilat"], "lng": r["trilong"], "city": r.get("city")}
    return None
```

### 9.3 BLE Device Scanning

**Hardware:** Same Raspberry Pi 4 (built-in BLE) or ESP32

**What it reveals:**
- Device names ("John's AirPods Pro" → first name)
- Apple Continuity protocol messages (device type, action state)
- Wearable signatures (Fitbit, Garmin, Apple Watch models)

```python
# backend/ambient/ble_scanner.py
# RESEARCH: bleak (4.5k★, async BLE library), bettercap (BLE+WiFi Swiss army knife)
# DECISION: bleak for Python integration, bettercap as standalone backup

from bleak import BleakScanner
from loguru import logger

async def scan_ble_devices(duration: float = 10.0) -> list[dict]:
    """Scan for nearby BLE devices and extract identifying info."""
    devices = await BleakScanner.discover(timeout=duration)
    results = []
    for d in devices:
        name = d.name or ""
        results.append({
            "mac": d.address,
            "name": name,
            "rssi": d.rssi,
            "inferred_owner": extract_owner_name(name),  # "John's AirPods" → "John"
            "device_type": classify_device(name),         # airpods, watch, phone, etc.
        })
    return results

def extract_owner_name(device_name: str) -> str | None:
    """Extract owner name from device names like 'John's AirPods Pro'."""
    import re
    match = re.match(r"^(.+?)['']s\s+", device_name)
    return match.group(1) if match else None
```

### 9.4 Ambient-to-Profile Correlation

The ambient layer feeds into the main profile pipeline:
1. WiFi probes → SSID analysis → workplace/school inference → add to person enrichment
2. BLE names → owner name extraction → cross-reference with detected faces by proximity + timing
3. Signal strength → proximity estimation → associate ambient data with nearest detected person

---

## 10. PUBLIC RECORDS AGENTS (Module: `backend/agents/public_records/`)

### 10.1 Overview
US public records are massive and largely free. These agents query federal/state databases to add depth no social-media-only tool can match.

### 10.2 Federal Database Agents

| Database | URL | Auth | What You Get |
|----------|-----|------|-------------|
| PACER (federal courts) | pacer.uscourts.gov | Account (free) | Federal court filings, lawsuits, bankruptcies |
| SEC EDGAR | efts.sec.gov/LATEST/search-index | None | Public company filings, insider trades, officer listings |
| FEC Donations | api.open.fec.gov | API key (free) | Political donations since 1977 — name, employer, amount |
| USPTO Patents | patentsview.org/api | None | Patent filings — inventor name, company, technology |
| SAM.gov Contracts | api.sam.gov | API key (free) | Government contracts — company, amount, scope |

### 10.3 State Database Agents

| Data Type | Coverage | Auth | Notes |
|-----------|----------|------|-------|
| Criminal Records | Per-county court sites | None/varies | Many counties have free online portals |
| Property Records | County assessor sites | None | Name → property ownership, value, purchase price |
| Professional Licenses | State boards | None | Doctors, lawyers, real estate agents, CPAs |
| Voter Registration | Secretary of State | Varies by state | Name, address, party affiliation, vote history |
| Business Registrations | Secretary of State | None | LLC/Corp filings — owner names, registered agents |

### 10.4 Implementation Pattern

```python
# backend/agents/public_records/fec_agent.py
# RESEARCH: FEC API is free, well-documented, no auth issues
# DECISION: Direct API calls — simple REST, returns JSON

import aiohttp
from loguru import logger

async def search_fec_donations(name: str, state: str = None) -> list[dict]:
    """Search FEC for political donations by name."""
    params = {"q": name, "sort": "-contribution_receipt_date", "per_page": 20}
    if state:
        params["contributor_state"] = state

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.open.fec.gov/v1/schedules/schedule_a/",
            params={**params, "api_key": config.FEC_API_KEY},
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            data = await resp.json()
            return [{
                "donor_name": r["contributor_name"],
                "amount": r["contribution_receipt_amount"],
                "date": r["contribution_receipt_date"],
                "employer": r.get("contributor_employer"),
                "committee": r["committee"]["name"],
            } for r in data.get("results", [])]
```

### 10.5 Aggregator Services (Browser Use Agents)

For data not available via API, use Browser Use to scrape:
- **FastPeopleSearch** — name → address, phone, relatives, associates (free, no login)
- **TruePeopleSearch** — similar to above
- **Spokeo** — aggregated public records (paid, but deep)
- **WhitePages** — address history, phone, relatives

These are Browser Use agents (3-8 sec each) that fire in parallel during Tier 2 enrichment.

---

## 11. LIVE CAMERA FEEDS (Module: `backend/ambient/cameras/`)

### 11.1 Overview
200,000+ publicly accessible camera feeds across the US. No authentication needed for most. Useful for venue-awareness during demo (show live feeds from nearby cameras on the corkboard).

### 11.2 Priority Camera APIs

| Source | Cameras | Auth | Refresh | API |
|--------|---------|------|---------|-----|
| Caltrans CWWP2 | 1,000+ | None | 15 sec | REST/JSON |
| NYC NYCTMC | 2,500+ | None | 2 sec | REST/JSON |
| State 511 Systems | 25+ states | Free key | 30 sec | REST/JSON |
| TrafficVision.Live | 135,000+ | None | Varies | Web scrape |

### 11.3 Caltrans API (California DOT)

```python
# backend/ambient/cameras/caltrans.py
# RESEARCH: Caltrans CWWP2 — free, no auth, JSON, 12 districts
# DECISION: Direct HTTP — dead simple

import aiohttp

CALTRANS_BASE = "https://cwwp2.dot.ca.gov/data"

async def get_caltrans_cameras(district: int = 4) -> list[dict]:
    """Get all camera feeds for a Caltrans district. District 4 = SF Bay Area."""
    url = f"{CALTRANS_BASE}/d{district}/cctv/cctvStatusD{district:02d}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            return [{
                "id": cam["cctv"]["index"],
                "name": cam["cctv"]["location"]["locationName"],
                "lat": cam["cctv"]["location"]["latitude"],
                "lng": cam["cctv"]["location"]["longitude"],
                "image_url": f"{CALTRANS_BASE}/d{district}/cctv/image/{cam['cctv']['index']}/{cam['cctv']['index']}.jpg",
                "direction": cam["cctv"]["location"].get("direction"),
            } for cam in data.get("data", [])]
```

### 11.4 NYC Traffic Cameras

```python
# backend/ambient/cameras/nyc.py
async def get_nyc_cameras() -> list[dict]:
    """Get all NYC traffic cameras. 2500+ cameras, no auth, 2s refresh."""
    url = "https://webcams.nyctmc.org/api/cameras"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            cameras = await resp.json()
            return [{
                "id": cam["id"],
                "name": cam["name"],
                "lat": cam["latitude"],
                "lng": cam["longitude"],
                "image_url": f"https://webcams.nyctmc.org/api/cameras/{cam['id']}/image",
            } for cam in cameras]
```

### 11.5 Demo Usage
During the live demo, show a mini-map on the corkboard with nearby camera feeds. This demonstrates environmental awareness and adds visual punch. The feeds refresh every 2-15 seconds — the judges see live images updating on the board.

---

## 12. EXPANDED OSINT TOOL INVENTORY

### 12.1 Username Enumeration (Tier 2 Agents)

| Tool | Sites | Speed | Install |
|------|-------|-------|---------|
| Sherlock | 400+ | ~30s | `pip install sherlock-project` |
| Maigret | 2,500+ | ~60s | `pip install maigret` |
| Social Analyzer | 1,000+ | ~45s | `pip install social-analyzer` |
| Blackbird | 600+ | ~20s | `pip install blackbird` |

**Strategy:** Run Sherlock (fastest) for quick results, Maigret in parallel for depth. If time permits, Social Analyzer as third pass.

### 12.2 Email Intelligence

| Tool | What It Does | Install |
|------|-------------|---------|
| Holehe | Check 120+ sites for email registration | `pip install holehe` |
| h8mail | Email → breach data, passwords | `pip install h8mail` |
| Hunter.io | Company email patterns + verification | API (free tier) |
| EmailRep | Email reputation + social profiles | API (free) |

### 12.3 Breach/Leak Databases

| Service | Records | API | Ethical Note |
|---------|---------|-----|-------------|
| Have I Been Pwned | 600M+ | Free REST | Only shows breach COUNT, not data |
| DeHashed | 7.5B+ | Paid REST | Full breach data — only show breach presence |
| LeakCheck | 7.5B+ | Paid REST | Similar to DeHashed |

**Demo framing:** "We found this person appears in 4 known data breaches" — demonstrates exposure without showing actual leaked data.

### 12.4 Comprehensive OSINT Frameworks

| Framework | Modules | Use Case |
|-----------|---------|----------|
| SpiderFoot (16k★) | 200+ | Automated full OSINT on a target |
| theHarvester (15k★) | Email, subdomain, name harvesting | Quick surface-level recon |
| Photon (12k★) | Web crawler extracting URLs, emails, files | Deep-crawl a person's website |
| Osintgram (12k★) | Instagram deep analysis | Profile, posts, followers, locations |
| CrossLinked | LinkedIn employee enumeration | Company → all employees |

### 12.5 Face Search API Details

| Service | API Type | Cost | Returns |
|---------|----------|------|---------|
| FaceCheck.ID | REST API | $0.30/search (3 credits) | Social profile URLs + similarity scores |
| PimEyes | Commercial API / Selenium scraper | ~$30/mo | Web URLs where face appears |
| PicImageSearch (652★) | Python lib | Free (uses Google/Yandex/Bing) | Multi-engine reverse image search |
| Lenso.ai | Web | Free tier | Face-focused reverse search |
| TinEye | REST API | Paid | Exact + modified image matches |

---

## 13. DEMO STRATEGY (From Operation Omniscience)

### 13.1 Pre-Consented Volunteer Approach
The demo subject appears to be a random person but is actually a pre-consented teammate or willing participant. This ensures:
- Ethical compliance (informed consent)
- Guaranteed data richness (pre-verified their profiles exist)
- No dead spots (we know the pipeline will find them)

### 13.2 Three-Minute Demo Script

| Time | Action | What Judges See |
|------|--------|----------------|
| 0:00-0:30 | Put on glasses, look at "random" volunteer | Face detected, card spawns on corkboard with photo |
| 0:30-1:30 | Agent swarm activates | 10+ Browser Use tabs fan out across LinkedIn, Twitter, GitHub, Google. Data streams into the card in real-time. Typewriter text effect. |
| 1:30-2:30 | Ambient data layer | WiFi probes show network history, BLE shows devices. Public records show donations, property. Connections drawn to other people on the board. |
| 2:30-3:00 | Pitch | "We built the world's first real-time person intelligence platform. Every data source you saw is publicly available. This is what's possible — and why privacy matters." |

### 13.3 Fallback Strategy
- **Pre-cached profiles:** 2-3 complete dossiers pre-loaded in Convex
- **Recorded video:** Screen recording of a successful end-to-end run
- **Staged sequence:** If live detection is slow, trigger the research manually with a pre-captured face

### 13.4 Sponsor Credit Utilization

| Sponsor | Credits | Usage |
|---------|---------|-------|
| Browser Use | $100 | Agent swarm (LinkedIn, Twitter, Google, PimEyes) |
| Vercel V0 | $50 | Frontend component generation |
| Convex | Free | Real-time database |
| MongoDB | Free | Persistent storage |
| Google DeepMind | $20 | Gemini 2.0 Flash for vision + synthesis |
| Daytona | $100 | Cloud dev environment |
| HUD | $200 | Multi-agent orchestration |
| Laminar | $150 | Agent tracing + observability |

---

## 14. ENVIRONMENT CONFIGURATION (Updated)

**Additional env vars for new modules:**

```python
# Add to backend/config.py Settings class:

    # Ambient Intelligence
    WIGLE_API_KEY: str = ""          # WiGLE SSID geolocation (free, 100/day)
    WIFI_INTERFACE: str = "wlan0mon" # Monitor-mode WiFi interface

    # Public Records
    FEC_API_KEY: str = ""            # FEC donation search (free)
    PACER_USERNAME: str = ""         # Federal court records
    PACER_PASSWORD: str = ""

    # Face Search
    FACECHECK_API_KEY: str = ""      # FaceCheck.ID API ($0.30/search)
    PIMEYES_ACCOUNTS: str = "[]"     # PimEyes account pool (JSON)

    # OSINT
    HUNTER_API_KEY: str = ""         # Hunter.io email lookup (free tier)
    EMAILREP_API_KEY: str = ""       # EmailRep (free)
    HIBP_API_KEY: str = ""           # Have I Been Pwned (free)
```
