# RESEARCH: No existing "person connection detector" libs found on PyPI/GitHub
# DECISION: Building custom — domain-specific scoring over dossier fields
# ALT: Could use NLP entity linking, but overkill for hackathon scope

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from synthesis.models import DossierReport


@dataclass(frozen=True)
class ConnectionCandidate:
    """A detected connection between two persons."""

    person_a_id: str
    person_b_id: str
    relationship_type: str  # "colleague" | "classmate" | "same_location" | "co_mentioned"
    confidence: float  # 0-1
    description: str
    evidence: list[str] = field(default_factory=list)


def detect_connections(
    new_person_id: str,
    new_dossier: DossierReport,
    existing_persons: list[dict],
) -> list[ConnectionCandidate]:
    """Compare a newly enriched person against all existing persons.

    Returns a list of ConnectionCandidate for any pair with confidence > 0.
    Each existing person dict must have keys: "person_id", "dossier" (DossierReport or dict).
    """
    candidates: list[ConnectionCandidate] = []

    for existing in existing_persons:
        existing_id = existing.get("person_id", "")
        if existing_id == new_person_id:
            continue

        existing_dossier = _extract_dossier(existing)
        if existing_dossier is None:
            continue

        connections = _compare_pair(
            new_person_id, new_dossier, existing_id, existing_dossier,
        )
        candidates.extend(connections)

    logger.info(
        "Connection detection: {} candidates found for person={}",
        len(candidates), new_person_id,
    )
    return candidates


def _extract_dossier(person: dict) -> DossierReport | None:
    """Pull a DossierReport from a person dict, handling both raw dict and model."""
    raw = person.get("dossier")
    if raw is None:
        return None
    if isinstance(raw, DossierReport):
        return raw
    if isinstance(raw, dict):
        try:
            return DossierReport(**raw)
        except Exception:
            return None
    return None


def _compare_pair(
    id_a: str,
    dossier_a: DossierReport,
    id_b: str,
    dossier_b: DossierReport,
) -> list[ConnectionCandidate]:
    """Run all comparison heuristics for a pair of dossiers."""
    results: list[ConnectionCandidate] = []

    colleague = _check_colleague(id_a, dossier_a, id_b, dossier_b)
    if colleague:
        results.append(colleague)

    classmate = _check_classmate(id_a, dossier_a, id_b, dossier_b)
    if classmate:
        results.append(classmate)

    location = _check_same_location(id_a, dossier_a, id_b, dossier_b)
    if location:
        results.append(location)

    co_mention = _check_co_mentioned(id_a, dossier_a, id_b, dossier_b)
    if co_mention:
        results.append(co_mention)

    return results


def _normalize(text: str) -> str:
    """Lowercase + strip for comparison."""
    return text.strip().lower()


def _check_colleague(
    id_a: str,
    dossier_a: DossierReport,
    id_b: str,
    dossier_b: DossierReport,
) -> ConnectionCandidate | None:
    """Check if two persons share a company in their work history."""
    companies_a = {_normalize(w.company) for w in dossier_a.work_history if w.company}
    companies_b = {_normalize(w.company) for w in dossier_b.work_history if w.company}

    # Also check current company field
    if dossier_a.company:
        companies_a.add(_normalize(dossier_a.company))
    if dossier_b.company:
        companies_b.add(_normalize(dossier_b.company))

    shared = companies_a & companies_b
    if not shared:
        return None

    # Higher confidence if current company matches
    current_a = _normalize(dossier_a.company) if dossier_a.company else ""
    current_b = _normalize(dossier_b.company) if dossier_b.company else ""
    is_current = current_a in shared or current_b in shared

    confidence = 0.85 if is_current else 0.6
    shared_list = sorted(shared)

    return ConnectionCandidate(
        person_a_id=id_a,
        person_b_id=id_b,
        relationship_type="colleague",
        confidence=confidence,
        description=f"Both worked at {', '.join(shared_list)}",
        evidence=[f"Shared company: {c}" for c in shared_list],
    )


def _check_classmate(
    id_a: str,
    dossier_a: DossierReport,
    id_b: str,
    dossier_b: DossierReport,
) -> ConnectionCandidate | None:
    """Check if two persons share a school in their education history."""
    schools_a = {_normalize(e.school) for e in dossier_a.education if e.school}
    schools_b = {_normalize(e.school) for e in dossier_b.education if e.school}

    shared = schools_a & schools_b
    if not shared:
        return None

    shared_list = sorted(shared)
    return ConnectionCandidate(
        person_a_id=id_a,
        person_b_id=id_b,
        relationship_type="classmate",
        confidence=0.7,
        description=f"Both attended {', '.join(shared_list)}",
        evidence=[f"Shared school: {s}" for s in shared_list],
    )


def _check_same_location(
    id_a: str,
    dossier_a: DossierReport,
    id_b: str,
    dossier_b: DossierReport,
) -> ConnectionCandidate | None:
    """Check if two persons mention the same location in their summaries."""
    # Extract location signals from summary text
    locations_a = _extract_location_signals(dossier_a.summary)
    locations_b = _extract_location_signals(dossier_b.summary)

    shared = locations_a & locations_b
    if not shared:
        return None

    shared_list = sorted(shared)
    return ConnectionCandidate(
        person_a_id=id_a,
        person_b_id=id_b,
        relationship_type="same_location",
        confidence=0.4,
        description=f"Both associated with {', '.join(shared_list)}",
        evidence=[f"Shared location signal: {loc}" for loc in shared_list],
    )


# Common city/region tokens to detect in summaries
_LOCATION_KEYWORDS = {
    "san francisco", "sf", "new york", "nyc", "los angeles", "la",
    "chicago", "seattle", "austin", "boston", "london", "berlin",
    "singapore", "tokyo", "bay area", "silicon valley", "palo alto",
    "mountain view", "menlo park", "sunnyvale", "cupertino",
}


def _extract_location_signals(text: str) -> set[str]:
    """Extract location keywords from text."""
    lower = text.lower()
    found: set[str] = set()
    for loc in _LOCATION_KEYWORDS:
        if loc in lower:
            found.add(loc)
    return found


def _check_co_mentioned(
    id_a: str,
    dossier_a: DossierReport,
    id_b: str,
    dossier_b: DossierReport,
) -> ConnectionCandidate | None:
    """Check if persons reference each other in notable activity or conversation hooks."""
    # We don't have person names here directly, so check for cross-references
    # in notable_activity and conversation_hooks by looking for company/school overlap
    # in those text fields
    all_text_a = " ".join(dossier_a.notable_activity + dossier_a.conversation_hooks).lower()
    all_text_b = " ".join(dossier_b.notable_activity + dossier_b.conversation_hooks).lower()

    # Check if any of B's companies/schools appear in A's activity text or vice versa
    b_entities = set()
    for w in dossier_b.work_history:
        if w.company:
            b_entities.add(_normalize(w.company))
    for e in dossier_b.education:
        if e.school:
            b_entities.add(_normalize(e.school))

    a_entities = set()
    for w in dossier_a.work_history:
        if w.company:
            a_entities.add(_normalize(w.company))
    for e in dossier_a.education:
        if e.school:
            a_entities.add(_normalize(e.school))

    cross_refs: list[str] = []
    for entity in b_entities:
        if entity and entity in all_text_a:
            cross_refs.append(entity)
    for entity in a_entities:
        if entity and entity in all_text_b:
            cross_refs.append(entity)

    if not cross_refs:
        return None

    unique_refs = sorted(set(cross_refs))
    return ConnectionCandidate(
        person_a_id=id_a,
        person_b_id=id_b,
        relationship_type="co_mentioned",
        confidence=0.5,
        description=f"Cross-referenced via {', '.join(unique_refs)}",
        evidence=[f"Co-mention: {r}" for r in unique_refs],
    )
