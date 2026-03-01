"use client";

import { useState, useCallback, useRef } from "react";
import type { Dossier, IntelPerson, IntelSource } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Strip noise from raw backend snippets */
function cleanSnippet(text: string): string {
  return text
    .replace(/\[Exa\]\s*/gi, "")
    .replace(/\[SixtyFour\]\s*/gi, "")
    .replace(/\[SixtyFour Deep\]\s*/gi, "")
    .replace(/={3,}/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** Map agent_name from backend to display-friendly source label + type.
 *  The card should show WHAT was found and WHERE, not which internal tool fetched it.
 *  When a URL is available, we derive the source name from the domain. */
function agentToSource(agentName: string, url?: string): { nm: string; tp: string } {
  // Type classification by agent
  const typeMap: Record<string, string> = {
    exa_deep: "WEB", sixtyfour_enrich: "PROFILE", sixtyfour_deep: "WEB",
    skill_tiktok_profile: "SOCIAL", skill_github_profile: "DEVELOPER",
    skill_instagram_posts: "SOCIAL", skill_linkedin_company_posts: "PROFESSIONAL",
    skill_facebook_page: "SOCIAL", skill_youtube_filmography: "MEDIA",
    skill_reddit_subreddit: "SOCIAL", skill_pinterest_pins: "SOCIAL",
    skill_linktree_profile: "SOCIAL", skill_osint_scraper: "OSINT",
    skill_sec_filings: "CORPORATE", skill_company_employees: "CORPORATE",
    skill_yc_company: "CORPORATE", skill_ancestry_records: "PUBLIC RECORD",
    skill_whois_lookup: "OSINT", deep_extract: "WEB", hibp_breach: "DARK WEB",
    wow_court_records: "PUBLIC RECORD", wow_political_donations: "PUBLIC RECORD",
    wow_academic_papers: "ACADEMIC", wow_podcast_appearances: "MEDIA",
    wow_crunchbase_profile: "CORPORATE",
  };

  // Domain-to-friendly-name mapping for common sources
  const domainNames: Record<string, string> = {
    "linkedin.com": "LinkedIn", "twitter.com": "Twitter", "x.com": "X (Twitter)",
    "instagram.com": "Instagram", "facebook.com": "Facebook", "github.com": "GitHub",
    "tiktok.com": "TikTok", "youtube.com": "YouTube", "reddit.com": "Reddit",
    "pinterest.com": "Pinterest", "crunchbase.com": "Crunchbase",
    "ycombinator.com": "Y Combinator", "medium.com": "Medium",
    "substack.com": "Substack", "sec.gov": "SEC Filings",
    "wikipedia.org": "Wikipedia", "en.wikipedia.org": "Wikipedia",
    "bloomberg.com": "Bloomberg", "techcrunch.com": "TechCrunch",
    "forbes.com": "Forbes", "nytimes.com": "New York Times",
    "wsj.com": "Wall Street Journal", "arxiv.org": "arXiv",
    "scholar.google.com": "Google Scholar", "producthunt.com": "Product Hunt",
    "angellist.com": "AngelList", "wellfound.com": "Wellfound",
    "glassdoor.com": "Glassdoor", "pitchbook.com": "PitchBook",
    "news.ycombinator.com": "Hacker News", "devpost.com": "Devpost",
    "kaggle.com": "Kaggle", "stackoverflow.com": "Stack Overflow",
    "npmjs.com": "npm", "pypi.org": "PyPI", "linktr.ee": "Linktree",
  };

  // Try to derive the name from the URL domain first
  let nm = "";
  if (url) {
    try {
      const hostname = new URL(url).hostname.replace("www.", "");
      // Check exact domain match
      nm = domainNames[hostname] ?? "";
      // If no exact match, try parent domain (e.g. "en.wikipedia.org" → "wikipedia.org")
      if (!nm) {
        const parts = hostname.split(".");
        if (parts.length > 2) {
          const parent = parts.slice(-2).join(".");
          nm = domainNames[parent] ?? "";
        }
      }
      // If still no match, use the domain capitalized
      if (!nm) {
        nm = hostname.split(".")[0].charAt(0).toUpperCase() + hostname.split(".")[0].slice(1);
        if (hostname.includes(".")) nm += "." + hostname.split(".").slice(1).join(".");
      }
    } catch { /* invalid URL, fall through */ }
  }

  // Fallback: use agent-name-based label
  if (!nm) {
    const fallbackMap: Record<string, string> = {
      exa_deep: "Web Intel", sixtyfour_enrich: "Profile Data",
      sixtyfour_deep: "Deep Search", deep_extract: "Web Extract",
      hibp_breach: "Data Breaches", skill_osint_scraper: "OSINT Scan",
    };
    const base = agentName.replace(/_retry$/, "");
    nm = fallbackMap[base] ?? "";
    if (!nm) {
      const cleaned = agentName.replace(/^skill_/, "").replace(/_/g, " ");
      nm = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
    }
  }

  const base = agentName.replace(/_retry$/, "");
  const tp = typeMap[base] ?? typeMap[agentName] ?? "INTEL";
  return { nm, tp };
}

/** Extract task_id and live_url from agent result profiles */
function extractAgentMeta(result: Record<string, unknown>): { taskId?: string; liveUrl?: string } {
  const profiles = (result.profiles ?? []) as Array<Record<string, unknown>>;
  for (const p of profiles) {
    const raw = p.raw_data as Record<string, string> | undefined;
    if (raw) {
      return {
        taskId: raw.task_id || undefined,
        liveUrl: raw.live_url || undefined,
      };
    }
  }
  // Fallback: check urls_found for live.browser-use.com URLs
  const urls = (result.urls_found ?? []) as string[];
  const liveUrl = urls.find((u) => u.includes("live.browser-use.com"));
  return { liveUrl };
}

export interface StreamState {
  isStreaming: boolean;
  person: IntelPerson | null;
  liveSessionId: string | null;
  liveUrl: string | null;
  error: string | null;
  totalSources: number;
}

export function useResearchStream() {
  const [state, setState] = useState<StreamState>({
    isStreaming: false,
    person: null,
    liveSessionId: null,
    liveUrl: null,
    error: null,
    totalSources: 0,
  });
  const abortRef = useRef<AbortController | null>(null);

  const startStream = useCallback((personName: string, imageUrl?: string) => {
    // Abort any existing stream
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({
      isStreaming: true,
      person: {
        id: "streaming",
        name: personName,
        status: "scanning",
        summary: {
          nm: personName.toUpperCase(),
          sm: "Scanning all sources...",
        },
        sources: [],
      },
      liveSessionId: null,
      liveUrl: null,
      error: null,
      totalSources: 0,
    });

    const params = new URLSearchParams();
    if (imageUrl) params.set("image_url", imageUrl);
    const url = `${API_BASE}/api/research/${encodeURIComponent(personName)}/stream${params.toString() ? "?" + params.toString() : ""}`;

    const eventSource = new EventSource(url);

    eventSource.addEventListener("init", (e) => {
      try {
        const data = JSON.parse(e.data);
        setState((prev) => ({
          ...prev,
          liveSessionId: data.live_session_id ?? null,
          liveUrl: data.live_url ?? null,
          person: prev.person
            ? {
                ...prev.person,
                id: data.person_id ?? prev.person.id,
                photoUrl: data.image_url ?? prev.person.photoUrl,
              }
            : prev.person,
        }));
      } catch { /* ignore parse errors */ }
    });

    eventSource.addEventListener("result", (e) => {
      try {
        const result = JSON.parse(e.data);
        const agentName: string = result.agent_name ?? "unknown";
        // Skip meta results (phase timings)
        if (agentName === "deep_researcher_meta") return;

        const snippets: string[] = result.snippets ?? [];
        const urlsFound: string[] = result.urls_found ?? [];
        const { taskId, liveUrl: agentLiveUrl } = extractAgentMeta(result);

        // Pick best URL: first non-live URL, or first URL
        const sourceUrl = urlsFound.find((u) => !u.includes("live.browser-use.com")) ?? urlsFound[0];
        // Derive source name from URL domain (not from internal tool name)
        const { nm, tp } = agentToSource(agentName, sourceUrl);

        // Use FULL snippet text (cleaned), not truncated
        const fullSnippet = snippets.map((s) => cleanSnippet(s)).join("\n\n");
        // Card preview — show enough context to be useful
        const cardSnippet = fullSnippet.slice(0, 500);

        const newSource: IntelSource = {
          nm,
          tp,
          sn: cardSnippet,
          url: sourceUrl,
          taskId: taskId,
          liveUrl: agentLiveUrl,
          sessionStatus: "completed",
        };

        setState((prev) => {
          if (!prev.person) return prev;
          const updatedSources = [...prev.person.sources, newSource];
          return {
            ...prev,
            totalSources: updatedSources.length,
            person: {
              ...prev.person,
              sources: updatedSources,
              summary: {
                ...prev.person.summary,
                sm: fullSnippet.length > 0
                  ? cleanSnippet(updatedSources.slice(0, 3).map((s) => s.sn).join(". ")).slice(0, 300)
                  : prev.person.summary.sm,
              },
            },
          };
        });
      } catch { /* ignore parse errors */ }
    });

    eventSource.addEventListener("dossier", (e) => {
      try {
        const data = JSON.parse(e.data) as Partial<Dossier>;
        setState((prev) => {
          if (!prev.person) return prev;
          return {
            ...prev,
            person: {
              ...prev.person,
              summary: {
                ...prev.person.summary,
                sm: data.summary ?? prev.person.summary.sm,
                title: data.title,
                location: data.company,
              },
              dossier: {
                summary: data.summary ?? "",
                title: data.title,
                company: data.company,
                workHistory: data.workHistory ?? [],
                education: data.education ?? [],
                socialProfiles: data.socialProfiles ?? {},
                notableActivity: data.notableActivity ?? [],
                conversationHooks: data.conversationHooks ?? [],
                riskFlags: data.riskFlags ?? [],
              },
            },
          };
        });
      } catch { /* ignore */ }
    });

    eventSource.addEventListener("complete", (e) => {
      try {
        const data = JSON.parse(e.data);
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          totalSources: data.total_sources ?? prev.totalSources,
          person: prev.person
            ? { ...prev.person, status: "complete" }
            : prev.person,
        }));
      } catch { /* ignore */ }
      eventSource.close();
    });

    eventSource.onerror = () => {
      setState((prev) => ({
        ...prev,
        isStreaming: false,
        error: "Connection lost",
      }));
      eventSource.close();
    };

    // Cleanup on abort
    controller.signal.addEventListener("abort", () => {
      eventSource.close();
    });
  }, []);

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...prev, isStreaming: false }));
  }, []);

  return { ...state, startStream, stopStream };
}
