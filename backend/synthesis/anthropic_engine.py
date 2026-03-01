# RESEARCH: anthropic python SDK (11k+ stars, official Anthropic SDK)
# DECISION: Using anthropic SDK directly -- official, well-maintained, async support
# ALT: litellm (unified interface) but adds unnecessary abstraction for a single fallback

from __future__ import annotations

import json

from loguru import logger

from config import Settings
from synthesis.models import (
    DossierReport,
    EducationEntry,
    SocialProfiles,
    SynthesisRequest,
    SynthesisResult,
    WorkHistoryEntry,
)

SYNTHESIS_PROMPT = """\
You are a person intelligence analyst. Given raw data about a person, \
synthesize a structured dossier.

Person name: {person_name}

Raw data sources:
{raw_data}

Produce a JSON object with EXACTLY these fields (no extra fields):
{{
  "summary": "2-3 sentence overview of who this person is",
  "title": "their current job title or primary role",
  "company": "their current company or organization",
  "work_history": [
    {{"role": "Job Title", "company": "Company Name", "period": "2020-present"}}
  ],
  "education": [
    {{"school": "University Name", "degree": "BS Computer Science"}}
  ],
  "social_profiles": {{
    "linkedin": "linkedin.com/in/username or null",
    "twitter": "@handle or null",
    "instagram": "@handle or null",
    "github": "github.com/username or null",
    "website": "example.com or null"
  }},
  "notable_activity": ["Recent notable things they have done"],
  "conversation_hooks": ["Interesting talking points to bring up in conversation"],
  "risk_flags": ["Any red flags or controversial associations, empty array if none"]
}}

Rules:
- Only include information supported by the raw data. Do not fabricate.
- If a field has no data, use empty string, empty array, or null.
- Keep summaries concise and factual.
- Conversation hooks should be specific and actionable.
- Risk flags should only include genuinely concerning items, not neutral facts.
- Return ONLY valid JSON, no markdown fencing, no explanation.
"""


class AnthropicSynthesisEngine:
    """Synthesizes person intelligence reports using Claude as a Gemini fallback."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._settings.anthropic_api_key)

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(
                api_key=self._settings.anthropic_api_key,
                timeout=30.0,
            )
        return self._client

    def _build_raw_data_block(self, request: SynthesisRequest) -> str:
        sections: list[str] = []

        if request.face_search_urls:
            sections.append("== Face Search URLs ==")
            for url in request.face_search_urls:
                sections.append(f"  - {url}")

        if request.enrichment_snippets:
            sections.append("== Enrichment Results ==")
            for snippet in request.enrichment_snippets:
                sections.append(f"  {snippet}")

        if request.social_profiles:
            sections.append("== Known Social Profiles ==")
            for sp in request.social_profiles:
                line = f"  - {sp.platform}: {sp.url}"
                if sp.username:
                    line += f" ({sp.username})"
                if sp.bio:
                    line += f" — {sp.bio}"
                sections.append(line)

        if request.raw_agent_data:
            for agent_name, data in request.raw_agent_data.items():
                sections.append(f"== {agent_name} Agent Data ==")
                sections.append(f"  {data}")

        if not sections:
            sections.append("No data available. Return empty/null fields.")

        return "\n".join(sections)

    def _parse_response(self, text: str, person_name: str) -> DossierReport:
        """Parse Claude JSON response into a DossierReport."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)

        work_history = [
            WorkHistoryEntry(
                role=entry.get("role", ""),
                company=entry.get("company", ""),
                period=entry.get("period") or None,
            )
            for entry in data.get("work_history", [])
            if entry.get("role") or entry.get("company")
        ]

        education = [
            EducationEntry(
                school=entry.get("school", ""),
                degree=entry.get("degree") or None,
            )
            for entry in data.get("education", [])
            if entry.get("school")
        ]

        sp_data = data.get("social_profiles", {})
        social_profiles = SocialProfiles(
            linkedin=sp_data.get("linkedin"),
            twitter=sp_data.get("twitter"),
            instagram=sp_data.get("instagram"),
            github=sp_data.get("github"),
            website=sp_data.get("website"),
        )

        return DossierReport(
            summary=data.get("summary", ""),
            title=data.get("title"),
            company=data.get("company"),
            work_history=work_history,
            education=education,
            social_profiles=social_profiles,
            notable_activity=data.get("notable_activity", []),
            conversation_hooks=data.get("conversation_hooks", []),
            risk_flags=data.get("risk_flags", []),
        )

    async def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """Synthesize enrichment data into a structured person report."""
        logger.info("AnthropicSynthesisEngine.synthesize person={}", request.person_name)

        if not self.configured:
            return SynthesisResult(
                person_name=request.person_name,
                success=False,
                error="Anthropic API key not configured (ANTHROPIC_API_KEY missing)",
            )

        try:
            raw_data = self._build_raw_data_block(request)
            prompt = SYNTHESIS_PROMPT.format(
                person_name=request.person_name,
                raw_data=raw_data,
            )

            client = self._get_client()
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text if response.content else ""
            if not response_text:
                return SynthesisResult(
                    person_name=request.person_name,
                    success=False,
                    error="Claude returned empty response",
                )

            dossier = self._parse_response(response_text, request.person_name)

            return SynthesisResult(
                person_name=request.person_name,
                summary=dossier.summary,
                occupation=dossier.title,
                organization=dossier.company,
                dossier=dossier,
                confidence_score=0.75,
            )

        except json.JSONDecodeError as e:
            logger.error("Failed to parse Claude response as JSON: {}", e)
            return SynthesisResult(
                person_name=request.person_name,
                success=False,
                error=f"Claude response was not valid JSON: {e}",
            )
        except Exception as e:
            logger.error("Anthropic synthesis failed: {}", e)
            return SynthesisResult(
                person_name=request.person_name,
                success=False,
                error=f"Synthesis error: {e}",
            )
