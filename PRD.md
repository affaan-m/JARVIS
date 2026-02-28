# Product Requirements Document: SPECTER
## Real-Time Person Intelligence Platform

**Version:** 0.1 | **Date:** 2026-02-27 | **Hackathon:** Web Agents Hackathon (Browser Use + YC)
**Team:** Affaan + Edmund | **Track:** Research Agent + Identify Leads & Send Targeted Outreach

---

## 1. One-Liner

A wearable-powered intelligence agent that identifies people in real-time via Meta glasses, deploys a swarm of browser agents to deep-research them across the internet, and streams results to a cinematic corkboard UI.

## 2. Problem

At events, conferences, and networking situations, you meet dozens of people but have zero context on who's worth your time. Current solutions (Google someone's name, check LinkedIn manually) are slow, shallow, and socially awkward. You want to know — in real-time — who someone is, what they've done, who they know, and whether they're worth a conversation.

## 3. Solution

SPECTER uses Meta Ray-Ban glasses to capture photos of people. A facial recognition pipeline identifies them, then a swarm of autonomous browser agents (powered by Browser Use) deep-researches each person across LinkedIn, X/Twitter, Instagram, Facebook, public records, and more. Results stream into a COD-style mission briefing corkboard where each person appears as a dossier with connections drawn between individuals.

## 4. Target User

- Founders at networking events who need to identify potential investors, partners, or hires
- Sales professionals at conferences who need to identify and qualify leads in real-time
- Anyone at a social/professional event who wants ambient intelligence about the people around them

## 5. Hackathon Judging Alignment

| Criteria | Weight | Our Play |
|----------|--------|----------|
| **Impact Potential** | 40% | Real-time person intelligence is a category-defining product. The "wow factor" of walking into a room and knowing everything about everyone is undeniable. Delivers extreme value to founders, salespeople, recruiters. |
| **Creativity** | 20% | COD-style corkboard UI, Meta glasses integration, swarm agent architecture, FBI-board aesthetic with live-streaming intel. Nothing like this exists. |
| **Technical Difficulty** | 20% | Multi-agent swarm orchestration, anti-bot detection bypass for PimEyes, parallel browser agents, real-time streaming pipeline, facial recognition integration, walled-garden data extraction. |
| **Demo & Presentation** | 20% | Live demo: put on glasses, look at a person, watch their dossier materialize on the corkboard in real-time. Backup video with cuts for slow parts. |

## 6. Core Features (MVP — 24 hours)

### P0 — Must Have
1. **Photo Capture Pipeline**: Meta glasses → photo → send to backend
2. **Facial Recognition**: PimEyes integration with parallel accounts for anti-bot
3. **Initial Report Generation**: LLM-powered summary from PimEyes results
4. **Browser Agent Swarm**: Deploy multiple Browser Use agents to deep-research each person
   - LinkedIn profile scraping
   - X/Twitter activity
   - Instagram (public profiles)
   - Google search aggregation
   - Exa API for structured research
5. **Corkboard UI**: COD/FBI-style mission board
   - Papers spawn in as data arrives
   - Click to zoom into individual dossiers
   - Draw-string connections between people
   - Real-time streaming updates
6. **Dossier View**: Per-person detail page with all gathered intelligence

### P1 — Should Have
7. **Relationship Mapping**: Identify connections between people (shared companies, schools, followers)
8. **Notification to Glasses**: Stream summary to Telegram/iMessage/web overlay viewable on Meta glasses
9. **Laminar Observability**: Tracing and evals to verify accuracy of gathered intel

### P2 — Nice to Have
10. **Conversation Audio Capture**: Record ambient conversations for additional context
11. **License Plate Recognition**: Vehicle identification for additional data points
12. **Walled-Garden Extraction**: Reverse-engineer internal APIs of gated platforms

## 7. Out of Scope (for hackathon)
- Mobile app
- User authentication / multi-user
- Data persistence beyond session
- GDPR/privacy compliance (it's a hackathon demo)

## 8. Success Metrics
- Identify and generate full dossier for 5+ people during live demo
- End-to-end latency: initial report < 30 seconds, deep research < 3 minutes
- Accuracy: zero obviously wrong information during demo (use Laminar for verification)
- Audience reaction: audible "wow" during demo

## 9. Technical Constraints
- **Time**: 20+ hours of build time (Feb 28 1PM → Mar 1 10AM)
- **Must use**: Browser Use (primary sponsor)
- **Should use**: Sponsor tools for credits/prizes (Exa, Laminar, Vercel, Convex, MongoDB)
- **Starting code**: Edmund's existing PimEyes → LLM report pipeline
- **Hardware**: Meta Ray-Ban glasses (need to source/buy)

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| PimEyes bot detection blocks us | High | Critical | Multiple accounts, rotating agents, rate limiting |
| Browser agents too slow for live demo | High | High | Pre-cache some results, video backup with cuts |
| Wrong information in demo | Medium | Critical | Laminar tracing for verification, manual review |
| Meta glasses integration issues | Medium | Medium | Fallback to phone camera + manual upload |
| Sponsor API rate limits | Low | Medium | Graceful degradation, queue management |

## 11. Sponsor Stack Usage Plan

| Sponsor | Usage | Credits |
|---------|-------|---------|
| **Browser Use** | Core agent orchestration — all browser automation | $100 |
| **Exa** | Structured person/company research API | Available via MCP |
| **Laminar** | Agent tracing, evals, accuracy verification | $150 |
| **Vercel** | Deploy corkboard frontend | $50 |
| **Convex** | Real-time database for streaming dossier updates | Free tier |
| **MongoDB** | Persistent storage for person data/reports | Free cluster |
| **Google DeepMind** | Gemini for LLM calls (report generation) | $20 |
| **OpenAI** | GPT-4o for vision (photo analysis) + research | Apply for credits |
| **HUD** | Agent observability/debugging | $200 |
| **Daytona** | Sandboxed environments for browser agents | $100 |
| **Supermemory** | Agent memory across research sessions | $100 |
| **VibeFlow** | Rapid UI prototyping for corkboard | $200 |

## 12. Prize Track Strategy

| Track | Auto-entered? | Strategy |
|-------|---------------|----------|
| Top 3 Overall | Yes | Go all-in on wow factor + technical depth |
| Founders Prize | Yes | Personal story: "We built what we wished we had at YC events" |
| Most Viral | Yes | Post demo video on X with #browser-use — the visual is inherently viral |
| Most Hardcore Infra | **Apply manually** | Multi-agent swarm, anti-bot, parallel processing — YES APPLY |
| Best Design | **Apply manually** | COD corkboard is visually stunning — YES APPLY |
| Best Use of Real-Time Data | **Apply manually** | Entire product is real-time streaming — YES APPLY |
| Best Devtool | Apply manually | Not really a devtool — SKIP |
