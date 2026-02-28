from __future__ import annotations

from pydantic import BaseModel, Field


class SocialProfile(BaseModel):
    """A linked social media profile."""

    platform: str
    url: str
    username: str | None = None
    bio: str | None = None
    followers: int | None = None


class ConnectionEdge(BaseModel):
    """A connection between the subject and another person."""

    person_name: str
    relationship: str
    context: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class WorkHistoryEntry(BaseModel):
    """A single work history entry matching frontend WorkHistoryEntry."""

    role: str
    company: str
    period: str | None = None


class EducationEntry(BaseModel):
    """A single education entry matching frontend EducationEntry."""

    school: str
    degree: str | None = None


class SocialProfiles(BaseModel):
    """Social profile links matching frontend SocialProfiles."""

    linkedin: str | None = None
    twitter: str | None = None
    instagram: str | None = None
    github: str | None = None
    website: str | None = None


class SynthesisRequest(BaseModel):
    """Input for report synthesis."""

    person_name: str
    face_search_urls: list[str] = Field(default_factory=list)
    enrichment_snippets: list[str] = Field(default_factory=list)
    social_profiles: list[SocialProfile] = Field(default_factory=list)
    raw_agent_data: dict[str, str] = Field(default_factory=dict)


class DossierReport(BaseModel):
    """Structured dossier matching the frontend Dossier interface exactly."""

    summary: str = ""
    title: str | None = None
    company: str | None = None
    work_history: list[WorkHistoryEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    social_profiles: SocialProfiles = Field(default_factory=SocialProfiles)
    notable_activity: list[str] = Field(default_factory=list)
    conversation_hooks: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

    def to_frontend_dict(self) -> dict:
        """Convert to camelCase dict matching frontend Dossier interface."""
        return {
            "summary": self.summary,
            "title": self.title,
            "company": self.company,
            "workHistory": [e.model_dump() for e in self.work_history],
            "education": [e.model_dump() for e in self.education],
            "socialProfiles": self.social_profiles.model_dump(exclude_none=True),
            "notableActivity": self.notable_activity,
            "conversationHooks": self.conversation_hooks,
            "riskFlags": self.risk_flags,
        }


class SynthesisResult(BaseModel):
    """Structured person intelligence report."""

    person_name: str
    summary: str = ""
    occupation: str | None = None
    organization: str | None = None
    location: str | None = None
    social_profiles: list[SocialProfile] = Field(default_factory=list)
    connections: list[ConnectionEdge] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    dossier: DossierReport | None = None
    success: bool = True
    error: str | None = None
