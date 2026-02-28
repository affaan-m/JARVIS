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
