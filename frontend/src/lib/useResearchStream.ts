"use client";

import { useState, useCallback, useRef } from "react";
import type { Dossier, IntelPerson, IntelSource } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Map agent_name from backend to display-friendly source label + type */
function agentToSource(agentName: string): { nm: string; tp: string } {
  const map: Record<string, { nm: string; tp: string }> = {
    exa_deep: { nm: "Exa Search", tp: "SEARCH" },
    sixtyfour_enrich: { nm: "SixtyFour.ai", tp: "ENRICHMENT" },
    sixtyfour_deep: { nm: "SixtyFour Deep Search", tp: "DEEP SEARCH" },
    skill_tiktok_profile: { nm: "TikTok Profile", tp: "SOCIAL" },
    skill_github_profile: { nm: "GitHub Profile", tp: "DEVELOPER" },
    skill_instagram_posts: { nm: "Instagram Posts", tp: "SOCIAL" },
    skill_linkedin_company_posts: { nm: "LinkedIn Profile", tp: "PROFESSIONAL" },
    skill_facebook_page: { nm: "Facebook Page", tp: "SOCIAL" },
    skill_youtube_filmography: { nm: "YouTube Channel", tp: "MEDIA" },
    skill_reddit_subreddit: { nm: "Reddit Profile", tp: "SOCIAL" },
    skill_pinterest_pins: { nm: "Pinterest Pins", tp: "SOCIAL" },
    skill_linktree_profile: { nm: "Linktree Links", tp: "SOCIAL" },
    skill_osint_scraper: { nm: "OSINT Scan", tp: "OSINT" },
    skill_sec_filings: { nm: "SEC Filings", tp: "CORPORATE" },
    skill_company_employees: { nm: "Company Employees", tp: "CORPORATE" },
    skill_yc_company: { nm: "YC Company", tp: "CORPORATE" },
    skill_ancestry_records: { nm: "Ancestry Records", tp: "PUBLIC RECORD" },
    skill_whois_lookup: { nm: "WHOIS Lookup", tp: "OSINT" },
    deep_extract: { nm: "Deep Extract", tp: "WEB" },
    hibp_breach: { nm: "Data Breaches", tp: "DARK WEB" },
  };
  if (map[agentName]) return map[agentName];
  // Strip "skill_" prefix for unknown skills
  const cleaned = agentName.replace(/^skill_/, "").replace(/_/g, " ");
  return { nm: cleaned.charAt(0).toUpperCase() + cleaned.slice(1), tp: "INTEL" };
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
            ? { ...prev.person, id: data.person_id ?? prev.person.id }
            : prev.person,
        }));
      } catch { /* ignore parse errors */ }
    });

    eventSource.addEventListener("result", (e) => {
      try {
        const result = JSON.parse(e.data);
        const agentName: string = result.agent_name ?? "unknown";
        const snippets: string[] = result.snippets ?? [];
        const urlsFound: string[] = result.urls_found ?? [];
        const confidence: number = result.confidence ?? 1.0;
        const { nm, tp } = agentToSource(agentName);

        const newSource: IntelSource = {
          nm,
          tp,
          sn: snippets[0]?.slice(0, 200) ?? "",
          url: urlsFound[0],
          sessionStatus: "completed",
        };

        setState((prev) => {
          if (!prev.person) return prev;
          const updatedSources = [...prev.person.sources, newSource];
          // Build an updating summary from all snippets
          const allSnippets = updatedSources.map((s) => s.sn).filter(Boolean);
          return {
            ...prev,
            totalSources: updatedSources.length,
            person: {
              ...prev.person,
              sources: updatedSources,
              summary: {
                ...prev.person.summary,
                sm: allSnippets.length > 0
                  ? allSnippets.slice(0, 3).join(" // ").slice(0, 300)
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
