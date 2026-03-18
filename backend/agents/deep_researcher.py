"""Deep researcher — unified pipeline that replaces the old orchestrator.

# RESEARCH: Exa returns 10 hits max per query. SixtyFour.ai adds structured
#   lead enrichment + agentic deep search. Combining them doubles discovery.
# DECISION: 4-phase async generator pipeline:
#   Phase 0: Exa multi-query + SixtyFour enrich-lead (parallel, ~3s)
#   Phase 1: Platform skills + OSINT skills (parallel, up to 15 concurrent)
#   Phase 2: Deep URL extraction + SixtyFour deep-search results + dark web
#   Phase 3: Verification loop — retry failed skills with account creation
# ALT: Keep old orchestrator (surface-level, no skill dispatch, no SixtyFour)
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from urllib.parse import urlparse

from loguru import logger

from agents.account_manager import AccountManager
from agents.cloud_skills import CloudSkillRunner
from agents.models import AgentResult, AgentStatus, ResearchRequest, SocialProfile
from config import Settings
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentRequest
from enrichment.sixtyfour_client import SixtyFourClient
from observability.laminar import traced

# Platform signup URLs for autonomous account creation
PLATFORM_SIGNUP_URLS = {
    "twitter.com": "https://x.com/i/flow/signup",
    "instagram.com": "https://www.instagram.com/accounts/emailsignup/",
    "tiktok.com": "https://www.tiktok.com/signup",
    "reddit.com": "https://www.reddit.com/register/",
    "github.com": "https://github.com/signup",
    "medium.com": "https://medium.com/m/signin?operation=register",
    "linkedin.com": "https://www.linkedin.com/signup",
}

# Map domains to Cloud SDK skill names for targeted extraction
DOMAIN_TO_SKILL = {
    "github.com": "github_profile",
    "tiktok.com": "tiktok_profile",
    "instagram.com": "instagram_posts",
    "facebook.com": "facebook_page",
    "reddit.com": "reddit_subreddit",
    "linkedin.com": "linkedin_company_posts",
    "youtube.com": "youtube_filmography",
    "linktree.com": "linktree_profile",
    "linktr.ee": "linktree_profile",
    "pinterest.com": "pinterest_pins",
}

# Map skill names to platform domains for signup retry
SKILL_TO_DOMAIN = {v: k for k, v in DOMAIN_TO_SKILL.items()}

# Max concurrency for Browser Use sessions
MAX_CONCURRENT_SESSIONS = 25

# Domains to skip from search results (noise)
SKIP_DOMAINS = frozenset({
    "digitalmarketingwithmustafaa.com",
    "wikipedia.org",
    "wikidata.org",
})


class DeepResearcher:
    """Multi-phase deep research pipeline that streams results.

    Phase 0: Exa + SixtyFour enrich-lead in parallel (~3s)
    Phase 1: Platform + OSINT skills in parallel (~20-35s, up to 15 concurrent)
    Phase 2: Deep URL extraction + SixtyFour deep-search + dark web (~30-60s)
    Phase 3: Verification loop — retry failed skills with account creation (~30-90s)

    Results stream as an async generator so the UI can update live.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._exa = ExaEnrichmentClient(settings)
        self._sixtyfour = SixtyFourClient(settings)
        self._cloud = CloudSkillRunner(settings)
        self._accounts = AccountManager(settings)
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_SESSIONS)

        # Load platform credentials from file (only verified entries)
        self._all_credentials: dict[str, dict] = {}
        creds_path = pathlib.Path(__file__).resolve().parent.parent / "agent_credentials.json"
        if creds_path.exists():
            try:
                raw = json.loads(creds_path.read_text())
                self._all_credentials = {
                    domain: cred for domain, cred in raw.items()
                    if cred.get("verified") is True
                }
                logger.info(
                    "deep_researcher: loaded {} verified credentials (of {} total)",
                    len(self._all_credentials), len(raw),
                )
            except Exception as exc:
                logger.warning("deep_researcher: failed to load credentials: {}", exc)

    def _secrets_for_skill(self, skill_name: str) -> dict[str, str] | None:
        """Return only the relevant platform credential for a skill.

        Browser Use Cloud throws 422 when >10 secrets are passed.
        This returns at most 1 entry: {domain: "email:password"}.
        """
        domain = SKILL_TO_DOMAIN.get(skill_name)
        if not domain:
            return None
        cred = self._all_credentials.get(domain)
        if not cred:
            return None
        return {domain: f"{cred['email']}:{cred['password']}"}

    def _augment_task_with_auth(self, skill_name: str, task_str: str) -> str:
        """Append auth instructions to a task prompt if we have credentials."""
        domain = SKILL_TO_DOMAIN.get(skill_name)
        if not domain:
            return task_str
        cred = self._all_credentials.get(domain)
        if not cred:
            return task_str
        auth_note = (
            f"\n\nAUTH: If you hit a login wall on {domain}, "
            f"log in with email '{cred['email']}' and password '{cred['password']}'. "
            f"If asked for a 2FA/OTP verification code, check the AgentMail inbox "
            f"at ciri@agentmail.to for the most recent 6-digit code."
        )
        return task_str + auth_note

    async def research(
        self,
        request: ResearchRequest,
    ) -> AsyncGenerator[AgentResult, None]:
        """Stream research results as they complete across all phases."""
        person = request.person_name
        company = request.company
        t0 = time.monotonic()
        seen_urls: set[str] = set()
        failed_skills: list[tuple[str, str]] = []  # (skill_name, task_str)
        phase_timings: dict[str, float] = {}

        # ── Phase 0: Exa FIRST (fast), SixtyFour in background ──────
        t_phase = time.monotonic()
        logger.info("deep_researcher: phase 0 — exa + sixtyfour for {}", person)

        # Run Exa queries immediately (these are fast, ~1s)
        exa_urls, exa_snippets = await self._exa_pass(person, company, seen_urls)

        # Yield Exa results IMMEDIATELY so frontend gets data in ~1s
        if exa_urls:
            yield AgentResult(
                agent_name="exa_deep",
                status=AgentStatus.SUCCESS,
                snippets=exa_snippets,
                urls_found=exa_urls,
                duration_seconds=time.monotonic() - t0,
            )

        # Start SixtyFour in background (don't wait — it's slow/unreliable)
        sixtyfour_result = None
        deep_search_task_id = None

        async def _sixtyfour_bg():
            nonlocal sixtyfour_result, deep_search_task_id
            try:
                sf_result, ds_id = await asyncio.gather(
                    self._sixtyfour.enrich_lead(person, company),
                    self._sixtyfour.start_deep_search(person),
                    return_exceptions=True,
                )
                if not isinstance(sf_result, Exception):
                    sixtyfour_result = sf_result
                if not isinstance(ds_id, Exception):
                    deep_search_task_id = ds_id
            except Exception as exc:
                logger.warning("sixtyfour background failed: {}", exc)

        sf_task = asyncio.create_task(_sixtyfour_bg())

        phase_timings["phase_0"] = round(time.monotonic() - t_phase, 2)
        logger.info(
            "deep_researcher: phase 0 fast pass done — {} exa URLs in {:.2f}s (sixtyfour running in bg)",
            len(exa_urls),
            phase_timings["phase_0"],
        )

        # ── Phase 1: Platform + OSINT skills in parallel ──────────────
        t_phase = time.monotonic()
        logger.info("deep_researcher: phase 1 — skills for {}", person)

        async for result in self._phase1(
            person, company, exa_urls, sixtyfour_result, seen_urls, failed_skills
        ):
            yield result

        phase_timings["phase_1"] = round(time.monotonic() - t_phase, 2)
        logger.info("deep_researcher: phase 1 done in {:.2f}s", phase_timings["phase_1"])

        # Check if SixtyFour finished by now (it ran in background during phase 1)
        try:
            await asyncio.wait_for(sf_task, timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            pass  # Don't block — move on

        if sixtyfour_result and getattr(sixtyfour_result, "success", False):
            sf_snippets, sf_urls, sf_profiles = [], [], []
            if sixtyfour_result.findings:
                sf_snippets.extend(f"[SixtyFour] {f}" for f in sixtyfour_result.findings)
            for attr, platform in [("linkedin", "linkedin"), ("twitter", "twitter"), ("github", "github"), ("instagram", "instagram")]:
                url = getattr(sixtyfour_result, attr, None)
                if url:
                    sf_urls.append(url)
                    sf_profiles.append(SocialProfile(platform=platform, url=url, display_name=sixtyfour_result.name or person))
            for attr, label in [("email", "Email"), ("phone", "Phone"), ("title", "Title"), ("company", "Company")]:
                val = getattr(sixtyfour_result, attr, None)
                if val:
                    sf_snippets.append(f"[SixtyFour] {label}: {val}")
            seen_urls.update(sf_urls)
            yield AgentResult(
                agent_name="sixtyfour_enrich",
                status=AgentStatus.SUCCESS,
                snippets=sf_snippets,
                urls_found=sf_urls,
                profiles=sf_profiles,
                duration_seconds=time.monotonic() - t0,
            )

        # ── Phase 2: Deep URL extraction + SixtyFour deep search + dark web
        t_phase = time.monotonic()
        logger.info("deep_researcher: phase 2 — deep extraction for {}", person)

        async for result in self._phase2(
            person, exa_urls, seen_urls, deep_search_task_id
        ):
            yield result

        phase_timings["phase_2"] = round(time.monotonic() - t_phase, 2)
        logger.info("deep_researcher: phase 2 done in {:.2f}s", phase_timings["phase_2"])

        # ── Phase 3: Verification loop — retry failed skills ──────────
        if failed_skills and self._accounts.configured:
            t_phase = time.monotonic()
            logger.info(
                "deep_researcher: phase 3 — retrying {} failed skills",
                len(failed_skills),
            )
            async for result in self._phase3(person, failed_skills):
                yield result
            phase_timings["phase_3"] = round(time.monotonic() - t_phase, 2)
            logger.info("deep_researcher: phase 3 done in {:.2f}s", phase_timings["phase_3"])

        elapsed = time.monotonic() - t0
        logger.info(
            "deep_researcher: completed for {} in {:.1f}s — timings={}",
            person, elapsed, phase_timings,
        )

        # Yield a final meta-result with phase timings for eval/observability
        yield AgentResult(
            agent_name="deep_researcher_meta",
            status=AgentStatus.SUCCESS,
            snippets=[f"phase_timings:{json.dumps(phase_timings)}"],
            duration_seconds=elapsed,
            confidence=1.0,
        )

    # ─── Phase 0: Exa + SixtyFour ────────────────────────────────────────

    @traced("deep_researcher.exa_pass", tags=["phase:0"])
    async def _exa_pass(
        self,
        person: str,
        company: str | None,
        seen_urls: set[str],
    ) -> tuple[list[str], list[str]]:
        """Run Exa queries only (fast, ~1s). Returns (urls, snippets)."""
        exa_queries = [
            EnrichmentRequest(name=person, company=company),
            EnrichmentRequest(name=person, additional_context="social media profiles"),
        ]
        if company:
            exa_queries.append(
                EnrichmentRequest(name=person, additional_context=f"{company} employee")
            )

        results = await asyncio.gather(
            *(self._exa.enrich_person(q) for q in exa_queries),
            return_exceptions=True,
        )

        exa_urls: list[str] = []
        exa_snippets: list[str] = []
        for result in results:
            if isinstance(result, Exception) or not result.success:
                continue
            for hit in result.hits:
                if not hit.url or hit.url in seen_urls:
                    continue
                domain = urlparse(hit.url).netloc.lower()
                if any(d in domain for d in SKIP_DOMAINS):
                    continue
                name_parts = person.lower().split()
                title_lower = (hit.title or "").lower()
                snippet_lower = (hit.snippet or "").lower()
                if not any(part in title_lower or part in snippet_lower for part in name_parts):
                    continue
                seen_urls.add(hit.url)
                exa_urls.append(hit.url)
                snippet = f"[Exa] {hit.title}: {hit.snippet[:200]}" if hit.snippet else f"[Exa] {hit.title}"
                exa_snippets.append(snippet)

        return exa_urls, exa_snippets

    async def _phase0(
        self,
        person: str,
        company: str | None,
        seen_urls: set[str],
    ) -> tuple[list[str], list[str], object | None, str | None]:
        """Run Exa multi-query + SixtyFour enrich-lead in parallel.

        Returns (exa_urls, exa_snippets, sixtyfour_result, deep_search_task_id).
        """
        exa_queries = [
            EnrichmentRequest(name=person, company=company),
            EnrichmentRequest(
                name=person,
                additional_context="social media profiles",
            ),
        ]
        if company:
            exa_queries.append(
                EnrichmentRequest(
                    name=person,
                    additional_context=f"{company} employee",
                )
            )

        # Fire all Phase 0 tasks in parallel
        exa_coros = [self._exa.enrich_person(q) for q in exa_queries]
        sixtyfour_coro = self._sixtyfour.enrich_lead(person, company)
        deep_search_coro = self._sixtyfour.start_deep_search(person)

        all_results = await asyncio.gather(
            *exa_coros,
            sixtyfour_coro,
            deep_search_coro,
            return_exceptions=True,
        )

        # Unpack
        exa_results = all_results[: len(exa_queries)]
        sixtyfour_result = all_results[len(exa_queries)]
        deep_search_task_id = all_results[len(exa_queries) + 1]

        if isinstance(sixtyfour_result, Exception):
            logger.warning("sixtyfour enrich-lead failed: {}", sixtyfour_result)
            sixtyfour_result = None
        if isinstance(deep_search_task_id, Exception):
            logger.warning("sixtyfour deep search start failed: {}", deep_search_task_id)
            deep_search_task_id = None

        # Parse Exa results
        exa_urls: list[str] = []
        exa_snippets: list[str] = []

        for result in exa_results:
            if isinstance(result, Exception) or not result.success:
                continue
            for hit in result.hits:
                if not hit.url or hit.url in seen_urls:
                    continue
                domain = urlparse(hit.url).netloc.lower()
                if any(d in domain for d in SKIP_DOMAINS):
                    continue
                # Relevance: at least one name part in title or snippet
                name_parts = person.lower().split()
                title_lower = (hit.title or "").lower()
                snippet_lower = (hit.snippet or "").lower()
                if not any(
                    part in title_lower or part in snippet_lower
                    for part in name_parts
                ):
                    continue
                seen_urls.add(hit.url)
                exa_urls.append(hit.url)
                snippet = (
                    f"[Exa] {hit.title}: {hit.snippet[:200]}"
                    if hit.snippet
                    else f"[Exa] {hit.title}"
                )
                exa_snippets.append(snippet)

        return exa_urls, exa_snippets, sixtyfour_result, deep_search_task_id

    # ─── Phase 1: Platform + OSINT skills ────────────────────────────────

    async def _phase1(
        self,
        person: str,
        company: str | None,
        exa_urls: list[str],
        sixtyfour_result: object | None,
        seen_urls: set[str],
        failed_skills: list[tuple[str, str]],
    ) -> AsyncGenerator[AgentResult, None]:
        """Run platform + OSINT skills in parallel."""
        skill_tasks: list[tuple[str, str, asyncio.Task]] = []

        # Core platform skills
        core_skills = [
            ("tiktok_profile", f"Get TikTok profile info for {person}"),
            ("github_profile", f"Get GitHub profile and projects for {person}"),
            ("instagram_posts", f"Get Instagram profile and posts for {person}"),
            (
                "linkedin_company_posts",
                f"Find LinkedIn profile and posts for {person}"
                + (f" at {company}" if company else ""),
            ),
            ("facebook_page", f"Get Facebook page or profile for {person}"),
            ("youtube_filmography", f"Find YouTube channel for {person}"),
            ("reddit_subreddit", f"Find Reddit profile for {person}"),
            ("pinterest_pins", f"Find Pinterest profile for {person}"),
            ("linktree_profile", f"Get Linktree links for {person}"),
        ]

        # OSINT skills
        osint_skills = [
            ("osint_scraper", f"Run OSINT search for {person}"),
        ]
        if company:
            osint_skills.extend([
                ("sec_filings", f"Find SEC filings for {company}"),
                ("company_employees", f"Find employees at {company}"),
                ("yc_company", f"Check if {company} is a YC company"),
            ])

        # Domain-matched skills from Exa/SixtyFour URLs
        domain_matched: list[tuple[str, str]] = []
        launched_skills: set[str] = set()

        for skill_name, task_str in core_skills + osint_skills:
            launched_skills.add(skill_name)

        for url in exa_urls:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            skill_name = DOMAIN_TO_SKILL.get(domain)
            if skill_name and skill_name not in launched_skills:
                domain_matched.append(
                    (skill_name, f"Extract all info from {url} about {person}")
                )
                launched_skills.add(skill_name)

        # Also check SixtyFour-discovered URLs
        if sixtyfour_result and hasattr(sixtyfour_result, "references"):
            for ref in sixtyfour_result.references or []:
                if not isinstance(ref, str) or not ref.startswith("http"):
                    continue
                domain = urlparse(ref).netloc.lower().replace("www.", "")
                skill_name = DOMAIN_TO_SKILL.get(domain)
                if skill_name and skill_name not in launched_skills:
                    domain_matched.append(
                        (skill_name, f"Extract info from {ref} about {person}")
                    )
                    launched_skills.add(skill_name)

        # Ancestry + whois (always run)
        always_skills = [
            ("ancestry_records", f"Find ancestry records for {person}"),
        ]

        all_skills = core_skills + osint_skills + domain_matched + always_skills

        # Launch all skill tasks with semaphore (augment with auth instructions)
        for skill_name, task_str in all_skills:
            augmented = self._augment_task_with_auth(skill_name, task_str)
            task = asyncio.ensure_future(
                self._run_skill_with_semaphore(skill_name, augmented)
            )
            skill_tasks.append((skill_name, task_str, task))

        # Gather all results then yield them (simpler than as_completed, no race conditions)
        task_objs = [t for _, _, t in skill_tasks]
        all_results = await asyncio.gather(*task_objs, return_exceptions=True)

        for idx, result in enumerate(all_results):
            sn, ts, _ = skill_tasks[idx]
            try:
                if isinstance(result, Exception):
                    logger.warning("deep_researcher: skill {} error: {}", sn, str(result))
                    failed_skills.append((sn, ts))
                    continue

                if result and result.get("success"):
                    output = result.get("output", "")
                    label = result.get("label", sn)
                    task_id = result.get("task_id", "")
                    live_url = result.get("live_url", "")
                    agent_result = AgentResult(
                        agent_name=f"skill_{label}",
                        status=AgentStatus.SUCCESS,
                        snippets=[output] if output else [],
                        urls_found=[live_url] if live_url else [],
                        profiles=[
                            SocialProfile(
                                platform=label,
                                url="",
                                display_name=person,
                                raw_data={
                                    "task_id": task_id,
                                    "live_url": live_url or "",
                                },
                            )
                        ],
                        confidence=self._compute_confidence(output, person),
                    )
                    if self._verify_result(agent_result, person):
                        yield agent_result
                    else:
                        logger.info(
                            "deep_researcher: filtered low-confidence skill_{}",
                            label,
                        )
                else:
                    failed_skills.append((sn, ts))

            except Exception as exc:
                logger.warning("deep_researcher: skill {} error: {}", sn, str(exc))
                failed_skills.append((sn, ts))

    # Slow platforms that need more time (login flows, heavy JS, etc.)
    _SLOW_SKILLS = frozenset({
        "linkedin_company_posts", "youtube_filmography", "pinterest_pins",
        "instagram_posts", "company_employees",
    })

    # Auth-heavy skills that need extra steps for login flows
    _AUTH_HEAVY_SKILLS = frozenset({
        "instagram_posts", "linkedin_company_posts", "facebook_page",
        "company_employees", "pinterest_pins",
    })

    @traced("deep_researcher.run_skill", tags=["phase:1"])
    async def _run_skill_with_semaphore(
        self, skill_name: str, task_str: str
    ) -> dict | None:
        """Run a skill task, respecting concurrency limit.

        Passes per-skill credentials (max 1-2 keys) to avoid >10 key 422 error.
        Uses higher max_steps for auth-heavy platforms that need login flows.
        """
        timeout = 120.0 if skill_name in self._SLOW_SKILLS else 60.0
        if skill_name in self._AUTH_HEAVY_SKILLS:
            max_steps = 15
        elif skill_name in self._SLOW_SKILLS:
            max_steps = 8
        else:
            max_steps = 5
        secrets = self._secrets_for_skill(skill_name)
        async with self._semaphore:
            return await self._cloud.run_skill(
                skill_name, task_str, timeout=timeout,
                max_steps=max_steps,
                secrets=secrets,
            )

    # ─── Phase 2: Deep extraction + SixtyFour deep search + dark web ─────

    async def _phase2(
        self,
        person: str,
        exa_urls: list[str],
        seen_urls: set[str],
        deep_search_task_id: str | None,
    ) -> AsyncGenerator[AgentResult, None]:
        """Deep URL extraction for uncovered URLs, SixtyFour deep search results, dark web."""
        tasks: list[asyncio.Task] = []
        task_labels: list[str] = []

        # Deep URL extractions (cap at 10)
        covered_domains = set(DOMAIN_TO_SKILL.keys())
        uncovered_urls = [
            url
            for url in exa_urls
            if urlparse(url).netloc.lower().replace("www.", "")
            not in covered_domains
        ][:10]

        for url in uncovered_urls:
            task = asyncio.ensure_future(
                self._deep_extract_with_semaphore(url, person)
            )
            tasks.append(task)
            task_labels.append(f"extract:{url[:60]}")

        # SixtyFour deep search results (if we started one in Phase 0)
        if deep_search_task_id:
            task = asyncio.ensure_future(
                self._sixtyfour.poll_deep_search(deep_search_task_id)
            )
            tasks.append(task)
            task_labels.append("sixtyfour_deep_search")

        # Dark web / HIBP breach check
        if self._settings.hibp_api_key:
            task = asyncio.ensure_future(
                self._cloud.run_skill(
                    "osint_scraper",
                    f"Check Have I Been Pwned for data breaches involving {person}",
                    timeout=30.0,
                )
            )
            tasks.append(task)
            task_labels.append("hibp_check")

        # High-impact freeform tasks (public records that wow judges)
        wow_tasks = [
            (
                "court_records",
                f"Go to courtlistener.com/? and search for '{person}'. "
                f"Extract any court cases, lawsuits, or legal filings. "
                f"Also try unicourt.com. Report all findings.",
            ),
            (
                "political_donations",
                f"Go to fec.gov/data/receipts/individual-contributions/ "
                f"and search for '{person}'. Extract all political donations — "
                f"amounts, recipients, dates, employer. Be thorough.",
            ),
            (
                "academic_papers",
                f"Go to scholar.google.com and search for '{person}'. "
                f"Extract all academic papers, citations, h-index, co-authors, "
                f"and research areas. Also check semanticscholar.org.",
            ),
            (
                "podcast_appearances",
                f"Go to listennotes.com and search for '{person}'. "
                f"Find any podcast episodes they appeared on or hosted. "
                f"Extract episode titles, show names, and dates.",
            ),
            (
                "crunchbase_profile",
                f"Go to crunchbase.com and search for '{person}'. "
                f"Extract: roles, companies founded/worked at, funding rounds, "
                f"investors, board positions, and exits.",
            ),
        ]
        for label, task_str in wow_tasks:
            async def _run_wow(lbl: str, prompt: str) -> dict | None:
                async with self._semaphore:
                    return await self._cloud.run_task(
                        prompt, max_steps=8, timeout=60.0,
                    )
            task = asyncio.ensure_future(_run_wow(label, task_str))
            tasks.append(task)
            task_labels.append(f"wow:{label}")

        # Gather all results (preserves order, unlike as_completed)
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        for idx, result in enumerate(all_results):
            try:
                if isinstance(result, Exception):
                    logger.warning("deep_researcher: phase 2 task error: {}", result)
                    continue
                label = task_labels[idx] if idx < len(task_labels) else "phase2"

                if label == "sixtyfour_deep_search":
                    # Parse deep search results (DeepSearchResult dataclass)
                    if result and getattr(result, "success", False) and getattr(result, "rows", []):
                        snippets = []
                        urls_found = []
                        for row in result.rows[:20]:
                            row_text = ", ".join(
                                f"{k}: {v}" for k, v in row.items() if v
                            )
                            snippets.append(f"[SixtyFour Deep] {row_text[:200]}")
                        urls_found = result.urls_found

                        yield AgentResult(
                            agent_name="sixtyfour_deep",
                            status=AgentStatus.SUCCESS,
                            snippets=snippets,
                            urls_found=urls_found,
                            confidence=0.8,
                            duration_seconds=0.0,
                        )

                elif label == "hibp_check":
                    if result and result.get("success"):
                        output = result.get("output", "")
                        yield AgentResult(
                            agent_name="hibp_breach",
                            status=AgentStatus.SUCCESS,
                            snippets=[output] if output else [],
                            confidence=0.9,
                        )

                elif label.startswith("wow:") and isinstance(result, dict) and result.get("success"):
                    output = result.get("output", "")
                    wow_name = label.replace("wow:", "")
                    task_id = result.get("task_id", "")
                    live_url = result.get("live_url", "")
                    # Strict verification for wow tasks — require FULL name
                    if not self._verify_result_strict(output, person):
                        logger.info("deep_researcher: wow_{} filtered — wrong person", wow_name)
                        continue
                    yield AgentResult(
                        agent_name=f"wow_{wow_name}",
                        status=AgentStatus.SUCCESS,
                        snippets=[output] if output else [],
                        urls_found=[live_url] if live_url else [],
                        profiles=[SocialProfile(
                            platform=wow_name,
                            url="",
                            display_name=person,
                            raw_data={"task_id": task_id, "live_url": live_url or ""},
                        )],
                        confidence=self._compute_confidence(output, person),
                    )

                elif isinstance(result, dict) and result.get("success"):
                    output = result.get("output", "")
                    source_url = label.replace("extract:", "")
                    task_id = result.get("task_id", "")
                    live_url = result.get("live_url", "")
                    yield AgentResult(
                        agent_name="deep_extract",
                        status=AgentStatus.SUCCESS,
                        snippets=[output] if output else [],
                        urls_found=[source_url] if source_url.startswith("http") else [],
                        profiles=[
                            SocialProfile(
                                platform="web",
                                url=source_url,
                                display_name=person,
                                raw_data={"task_id": task_id, "live_url": live_url or ""},
                            )
                        ] if source_url.startswith("http") else [],
                        confidence=self._compute_confidence(output, person),
                    )

            except Exception as exc:
                logger.warning("deep_researcher: phase 2 error: {}", str(exc))

    @traced("deep_researcher.deep_extract", tags=["phase:2"])
    async def _deep_extract_with_semaphore(
        self, url: str, person: str
    ) -> dict | None:
        async with self._semaphore:
            # Pass secrets for deep extraction too (some URLs need auth)
            task = (
                f"Navigate to {url} and extract ALL information about "
                f"'{person}'. Get: full name, title, bio, company, "
                f"social links, achievements, education, publications, "
                f"contact info, photos, and any other relevant data. "
                f"Be thorough — extract everything visible on the page."
            )
            return await self._cloud.run_task(
                task, max_steps=8, timeout=60.0,
            )

    # ─── Phase 3: Verification loop + account creation ───────────────────

    async def _phase3(
        self,
        person: str,
        failed_skills: list[tuple[str, str]],
    ) -> AsyncGenerator[AgentResult, None]:
        """Retry failed skills with auth — check saved credentials first."""
        for skill_name, task_str in failed_skills:
            domain = SKILL_TO_DOMAIN.get(skill_name)
            if not domain:
                continue

            # Check saved verified credentials FIRST (avoids account creation)
            cred = self._all_credentials.get(domain)
            if cred:
                creds = {"email": cred["email"], "password": cred["password"]}
            else:
                # Fall back to account creation
                signup_url = PLATFORM_SIGNUP_URLS.get(domain)
                if not signup_url:
                    continue
                creds = await self._accounts.ensure_account(
                    domain, signup_url, person_name="Jarvis Agent"
                )

            if not creds:
                logger.info(
                    "deep_researcher: no creds for {}, skipping retry",
                    domain,
                )
                continue

            # Augment task with auth instructions and retry
            augmented = self._augment_task_with_auth(skill_name, task_str)
            logger.info(
                "deep_researcher: retrying {} with auth ({})",
                skill_name,
                creds.get("email"),
            )
            try:
                async with self._semaphore:
                    result = await self._cloud.run_skill(
                        skill_name,
                        augmented,
                        timeout=120.0,
                        max_steps=20,
                        secrets={
                            domain: f"{creds['email']}:{creds['password']}"
                        },
                    )

                if result and result.get("success"):
                    output = result.get("output", "")
                    task_id = result.get("task_id", "")
                    live_url = result.get("live_url", "")
                    yield AgentResult(
                        agent_name=f"skill_{skill_name}_retry",
                        status=AgentStatus.SUCCESS,
                        snippets=[output] if output else [],
                        profiles=[
                            SocialProfile(
                                platform=skill_name,
                                url="",
                                display_name=person,
                                raw_data={"cloud_output": output, "authenticated": True},
                            )
                        ],
                        confidence=self._compute_confidence(output, person),
                    )
            except Exception as exc:
                logger.warning(
                    "deep_researcher: retry failed for {}: {}",
                    skill_name,
                    exc,
                )

    # ─── Verification helpers ────────────────────────────────────────────

    @staticmethod
    def _verify_result(result: AgentResult, person_name: str) -> bool:
        """Check if a result is about the target person.

        At least one name part must appear in the combined text output.
        Results with no snippets pass (they may have profiles with correct data).
        """
        if not result.snippets:
            return True

        name_parts = person_name.lower().split()
        all_text = " ".join(result.snippets).lower()
        return any(part in all_text for part in name_parts)

    @staticmethod
    def _verify_result_strict(output: str, person_name: str) -> bool:
        """Strict verification — ALL name parts must appear in output.

        Used for wow tasks (court records, political donations etc.) that
        grab whatever they find on the page, often for wrong people.
        """
        if not output:
            return False
        output_lower = output.lower()
        name_parts = person_name.lower().split()
        return all(part in output_lower for part in name_parts)

    @staticmethod
    def _compute_confidence(output: str, person_name: str) -> float:
        """Compute confidence score based on name match strength."""
        if not output:
            return 0.3

        output_lower = output.lower()
        name_parts = person_name.lower().split()
        matched = sum(1 for part in name_parts if part in output_lower)

        if matched == 0:
            return 0.1
        if matched == len(name_parts):
            # Full name match
            return 1.0
        return 0.3 + (0.7 * matched / len(name_parts))
