# JARVIS — Design Handoff: Frontend / UX / Visual
## For Frontend Coding Agent Handoff

**Version:** 0.1 | **Date:** 2026-02-28 | **Status:** READY TO BUILD

---

## 0. Design Philosophy

JARVIS's UI is a **Call of Duty: Black Ops mission briefing war room**. Think the evidence board from Black Ops Cold War's safehouse — green-tinted fluorescent lighting, brick walls, military filing cabinets, classified documents pinned to a board with red string connecting targets. NOT a cozy Pinterest corkboard — this is a military intelligence operation.

**Primary visual reference:** COD Black Ops Cold War "Evidence Board" — green military tint over everything, harsh fluorescent overhead lighting, brick/concrete walls, metal shelving with file boxes, photos and documents pinned with red string, maps with location markers, analog + classified aesthetic.

**Core principles:**
1. **Military operations center** — green-tinted lighting, concrete/brick textures, metal surfaces, classified stamps, redacted text
2. **Information density** — show a LOT of data per card, but layered (overview → click to expand)
3. **Motion = life** — papers slide in, pins bounce, strings draw themselves, data typewriter-fills
4. **Green + dark palette** — military green tint over the board, harsh lighting contrast, no warm tones
5. **Classified atmosphere** — [REDACTED] blocks, "TOP SECRET" stamps, file folder tabs, evidence numbering

---

## 1. Color System

```
/* Core palette — COD Black Ops military green */
--bg-dark:          #0a0d08;        /* App background — near-black with green undertone */
--bg-chrome:        #141a12;        /* UI chrome panels — dark military green */
--board-bg:         #2a2f25;        /* Evidence board background — dark olive/concrete */
--board-wall:       #3d3529;        /* Brick wall texture tint */
--paper:            #d4cdb8;        /* Dossier paper — aged manila folder */
--paper-aged:       #c4b998;        /* More aged paper variant */
--paper-shadow:     rgba(0,0,0,0.4);

/* Military green lighting overlay */
--fluorescent:      rgba(120,180,80,0.06); /* Green fluorescent light wash */
--fluorescent-hot:  rgba(140,200,90,0.12); /* Brighter green for focal areas */

/* Accent colors */
--red-string:       #c0392b;        /* Connection lines (THE red string) */
--red-glow:         rgba(192,57,43,0.4);
--pin-red:          #e74c3c;        /* Pushpin heads */
--pin-steel:        #7f8c8d;        /* Metal pin / thumbtack */
--highlight-yellow: #e8d44d;        /* Highlighter on paper — harsher yellow */
--stamp-red:        #b03020;        /* "CLASSIFIED" / "TOP SECRET" stamp — darker, more military */
--redacted-black:   #1a1a1a;        /* [REDACTED] blocks */

/* Status colors */
--status-pending:   #f39c12;        /* Amber — identifying */
--status-active:    #5dade2;        /* Light blue — researching */
--status-complete:  #27ae60;        /* Green — dossier complete */
--status-error:     #e74c3c;        /* Red — failed */

/* Text */
--text-primary:     #1a1a1a;        /* On paper — near black */
--text-secondary:   #4a4a4a;        /* On paper, secondary */
--text-ui:          #c8d6b0;        /* On dark chrome — greenish white */
--text-ui-dim:      #6b7a5e;        /* On dark chrome, secondary — muted olive */
--text-classified:  #b03020;        /* Stamp text */
--text-redacted:    #1a1a1a;        /* Black bars over text */

/* Typewriter font for dossier text */
--font-typewriter:  'Courier Prime', 'Courier New', monospace;
--font-ui:          'Inter', system-ui, sans-serif;
--font-heading:     'Bebas Neue', 'Impact', sans-serif;  /* Military stencil feel */
```

---

## 2. Typography

| Element | Font | Size | Weight | Notes |
|---------|------|------|--------|-------|
| Person name on card | Bebas Neue | 18px | 400 | ALL CAPS, letter-spacing: 2px |
| Dossier body text | Courier Prime | 13px | 400 | Typewriter feel, line-height: 1.6 |
| UI labels | Inter | 12px | 500 | Uppercase, tracking wide |
| Status badges | Inter | 10px | 700 | Uppercase, colored pill |
| "CLASSIFIED" stamp | Bebas Neue | 28px | 400 | Rotated -12deg, stamp-red, opacity 0.7 |
| Live feed items | Inter | 13px | 400 | Normal case |

Google Fonts to load: `Courier+Prime`, `Bebas+Neue`, `Inter`

---

## 3. Layout Structure

```
┌──────────────────────────────────────────────────────────────┐
│ TOP BAR (fixed, 48px)                                         │
│ ┌─────────┬────────────────────────────┬──────────┬─────────┐│
│ │ JARVIS │ [status indicator: agents]  │ [clock]  │ [•••]  ││
│ │ logo    │ "4 agents active"           │ 14:32:07 │ menu   ││
│ └─────────┴────────────────────────────┴──────────┴─────────┘│
├──────────────────────────────────────────────┬───────────────┤
│                                              │               │
│              CORKBOARD CANVAS                │  LIVE FEED    │
│              (scrollable, pannable)          │  SIDEBAR      │
│                                              │  (320px)      │
│  ┌──────┐          ┌──────┐                  │               │
│  │PERSON│──string──│PERSON│                  │ ● Identified  │
│  │CARD  │          │CARD  │                  │   John Doe    │
│  └──────┘          └──────┘                  │   12:31:04    │
│                         │                    │               │
│              string─────┘                    │ ● Researching │
│                    │                         │   Jane Smith  │
│               ┌──────┐                       │   12:31:12    │
│               │PERSON│                       │               │
│               │CARD  │                       │ ● LinkedIn    │
│               └──────┘                       │   data found  │
│                                              │   12:31:18    │
│                                              │               │
├──────────────────────────────────────────────┴───────────────┤
│ BOTTOM STATUS BAR (32px)                                      │
│ "3 persons identified | 12 agents deployed | PimEyes: ready" │
└──────────────────────────────────────────────────────────────┘
```

### Responsive Notes
- **Demo mode (primary):** 1920x1080 or 2560x1440 — optimized for projector/screen share
- Corkboard is pannable with mouse drag, zoomable with scroll
- Mobile is completely out of scope

---

## 4. Component Specifications

### 4.1 PersonCard (on corkboard)

```
┌─────────────────────────────┐ ← paper texture bg, slight rotation (-3 to +3 deg)
│  📌 (pushpin at top-center) │ ← red or yellow pin, drop shadow
│                             │
│  ┌──────────┐  JOHN DOE    │ ← Bebas Neue, caps
│  │          │  ──────────  │
│  │  PHOTO   │  CTO @ Acme  │ ← Courier Prime, smaller
│  │  (80x80) │  San Fran.   │
│  └──────────┘              │
│                             │
│  ● LinkedIn ● Twitter      │ ← small icons, colored if found
│                             │
│  [STATUS BADGE]             │ ← "RESEARCHING" / "COMPLETE"
│                             │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │ ← torn paper edge at bottom
└─────────────────────────────┘
  Width: 220px | Height: ~280px (varies)
  Drop shadow: 4px 4px 12px rgba(0,0,0,0.4)
  Border: none (paper edge)
  Rotation: random(-3deg, 3deg) — set on spawn, fixed after
```

**States:**
- `pending` — paper is blank/loading, pulsing glow
- `identified` — photo + name appear (typewriter animation for name)
- `researching` — status badge pulses blue, data fills in incrementally
- `complete` — "CLASSIFIED" stamp appears (rotate animation), all data present

**Interaction:**
- Hover: slight lift (translateY: -4px, shadow increases)
- Click: opens DossierView (see 4.3)

### 4.2 ConnectionLine (red string)

```css
/* SVG path between two PersonCards */
.connection-line {
  stroke: var(--red-string);
  stroke-width: 2;
  stroke-dasharray: 8 4;      /* dashed for "string" feel */
  filter: drop-shadow(0 0 3px var(--red-glow));
  animation: drawString 1.5s ease-out forwards;
}

@keyframes drawString {
  from { stroke-dashoffset: 100%; }
  to   { stroke-dashoffset: 0; }
}
```

- Lines connect center of card A to center of card B
- Small label at midpoint: "Co-workers @ Google" in tiny Inter font
- Lines should curve slightly (quadratic bezier) — not perfectly straight
- On hover of a card, its connections glow brighter

### 4.3 DossierView (expanded panel)

When you click a PersonCard, a side panel slides in from the right (or the card zooms/expands — your call as implementer, but panel is easier).

```
┌──────────────────────────────────────────┐
│ DOSSIER: JOHN DOE            [✕ close]   │  ← dark chrome header
├──────────────────────────────────────────┤
│                                          │
│  ┌────────────┐                          │
│  │   PHOTO    │  JOHN MICHAEL DOE        │  ← large name
│  │  (150x150) │  Chief Technology Officer │
│  │            │  Acme Corp               │
│  └────────────┘  San Francisco, CA       │
│                                          │
│  ══════════════════════════════════════  │
│  WORK HISTORY                            │  ← section headers in Bebas Neue
│  ──────────────────────────────────────  │
│  ● CTO — Acme Corp (2022-present)       │  ← Courier Prime
│  ● Sr. Engineer — Google (2018-2022)     │
│  ● Engineer — Startup X (2015-2018)     │
│                                          │
│  ══════════════════════════════════════  │
│  EDUCATION                               │
│  ──────────────────────────────────────  │
│  ● MS Computer Science — Stanford        │
│  ● BS Mathematics — MIT                  │
│                                          │
│  ══════════════════════════════════════  │
│  SOCIAL PROFILES                         │
│  ──────────────────────────────────────  │
│  🔗 linkedin.com/in/johndoe             │
│  🐦 @johndoe (12.4k followers)          │
│  📸 @johndoe.ig                          │
│                                          │
│  ══════════════════════════════════════  │
│  CONVERSATION HOOKS                      │  ← THE killer feature
│  ──────────────────────────────────────  │
│  → Ask about their recent Series B       │
│  → They posted about AI agents last week │
│  → Stanford alumni — check mutual conns  │
│                                          │
│  ══════════════════════════════════════  │
│  NOTABLE ACTIVITY                        │
│  ──────────────────────────────────────  │
│  • Tweeted about Browser Use 3 days ago  │
│  • Spoke at AI Summit 2025               │
│  • Open source contributor (2.1k stars)  │
│                                          │
│  ══════════════════════════════════════  │
│  ⚠️ RISK FLAGS                           │
│  ──────────────────────────────────────  │
│  • Previously associated with [company]  │
│  • Pending litigation (public record)    │
│                                          │
└──────────────────────────────────────────┘
  Width: 480px (fixed)
  Background: var(--bg-chrome)
  Slides in from right, 300ms ease-out
  Scrollable content area
```

### 4.4 LiveFeed (sidebar)

Real-time activity stream. Each event is a small card:

```
┌────────────────────────────────┐
│ ● 12:31:04                     │  ← colored dot = status color
│ Identified: John Doe           │
│ via PimEyes (87% confidence)   │  ← dim text
├────────────────────────────────┤
│ 🔍 12:31:12                    │
│ LinkedIn agent deployed        │
│ for John Doe                   │
├────────────────────────────────┤
│ ✅ 12:31:28                    │
│ LinkedIn data received         │
│ CTO @ Acme Corp               │
└────────────────────────────────┘
```

- New events slide in from top, push others down
- Max ~50 visible, older ones fade out
- Subtle pulse animation on new event arrival
- Clicking an event scrolls corkboard to relevant card

### 4.5 TopBar

```
┌────────────────────────────────────────────────────────────┐
│ 👁 JARVIS    ▓▓▓░░ 4 agents active    14:32:07   [⚙️]   │
└────────────────────────────────────────────────────────────┘
```

- Logo: eye icon + "JARVIS" in Bebas Neue, letter-spaced
- Agent status: mini progress bars or activity dots
- Clock: monospace, updating every second (military time)
- Settings gear: opens config modal (API keys, etc.) — low priority

### 4.6 StatusBar (bottom)

```
┌────────────────────────────────────────────────────────────┐
│ 3 persons identified │ 12 agents deployed │ PimEyes: ● OK  │
└────────────────────────────────────────────────────────────┘
```

- Small, unobtrusive, monospace text
- Status dots for each service (green/yellow/red)

---

## 5. Animation Specifications

### 5.1 Card Spawn Animation
When a new person is identified and their card appears on the corkboard:

```typescript
// Framer Motion variant
const cardSpawn = {
  initial: {
    scale: 0,
    opacity: 0,
    rotate: random(-15, 15),
    y: -100,
  },
  animate: {
    scale: 1,
    opacity: 1,
    rotate: random(-3, 3),  // final resting rotation
    y: 0,
    transition: {
      type: "spring",
      stiffness: 300,
      damping: 20,
      duration: 0.6,
    },
  },
};

// Pin drop (slightly delayed)
const pinDrop = {
  initial: { scale: 0, y: -30 },
  animate: {
    scale: 1,
    y: 0,
    transition: { delay: 0.4, type: "spring", stiffness: 500, damping: 15 },
  },
};
```

**Sequence:**
1. Card flies in from above (0-400ms)
2. Pin drops onto card (400-600ms)
3. Card settles with slight bounce (600-800ms)
4. Name typewriter-fills (800-1200ms)
5. Data fields fade in sequentially (1200ms+)

### 5.2 String Draw Animation
When a connection is detected between two people:

1. Line starts from card A center
2. SVG path draws toward card B over 1.5s (stroke-dashoffset animation)
3. Small label fades in at midpoint (delay: 1.2s)
4. Brief red glow pulse on both connected cards

### 5.3 Data Streaming Effect
As research data comes in for a person's card:

- New text fields appear with a **typewriter effect** (character by character, 30ms/char)
- Use Framer Motion's `animate` with staggered children
- Status badge transitions with a flip animation

### 5.4 "CLASSIFIED" Stamp
When dossier is complete:

```typescript
const stampAnimation = {
  initial: { scale: 3, opacity: 0, rotate: -25 },
  animate: {
    scale: 1,
    opacity: 0.7,
    rotate: -12,
    transition: { type: "spring", stiffness: 200, damping: 10 },
  },
};
```

---

## 6. Corkboard Canvas Implementation

### 6.1 Technology
- **Canvas approach:** CSS transforms on a container div (NOT HTML5 canvas — we need DOM elements for React)
- **Pan:** Mouse drag on background translates the container
- **Zoom:** Scroll wheel scales the container (min: 0.3, max: 2.0)
- Library: None needed. CSS transform + mouse events. Or use `@use-gesture/react` for smoother pan/zoom.

### 6.2 Cork Texture
- Use a repeating CSS background image of cork texture
- Subtle CSS noise overlay for depth: `background-image: url('/cork-texture.jpg')`
- Source a free cork texture (2048x2048 seamless tileable) or generate with CSS gradients

### 6.3 Card Placement
- Backend provides `boardPosition: {x, y}` for each person
- First person: center of viewport
- Subsequent: placed in a loose grid/cluster around existing cards
- Cards should NOT overlap (collision detection — simple bounding box check)
- Drag-to-reposition is nice-to-have but NOT required for demo

---

## 7. Convex Real-Time Integration

### 7.1 Subscription Pattern
```typescript
// Frontend subscribes to all persons
const persons = useQuery(api.persons.listAll);
const connections = useQuery(api.connections.listAll);
const liveFeed = useQuery(api.intel.recentActivity, { limit: 50 });

// Each person card auto-updates when backend mutates
// Convex handles WebSocket subscriptions automatically
```

### 7.2 Optimistic Updates
- When capture is submitted, immediately show a "pending" card on the board
- When identification returns, animate the transition from pending → identified
- When research completes, stream in each field as it arrives

---

## 8. Asset Requirements

| Asset | Source | Format | Notes |
|-------|--------|--------|-------|
| Cork texture | Free stock / Unsplash | JPG, 2048x2048, seamless | Tileable background |
| Pushpin | SVG or CSS | SVG preferred | Red + yellow variants |
| Paper texture | CSS or PNG | Optional overlay | Subtle fiber/grain |
| Eye logo | SVG | Inline SVG | Simple eye icon for JARVIS brand |
| Torn paper edge | CSS or SVG mask | Bottom of cards | clip-path or mask-image |

### Fonts (Google Fonts CDN)
```html
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Courier+Prime&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

---

## 9. Demo-Specific UX Notes

1. **Pre-seed 2-3 people** before demo starts so the board isn't empty
2. **"Camera" button** in the top bar for manual photo upload (fallback if glasses fail)
3. **Sound effects** (optional but high-impact): camera shutter on capture, paper rustle on card spawn, typewriter clicks on text fill
4. **Full-screen mode** — hide browser chrome for cleaner demo (F11 or Vercel preview mode)
5. **Speed controls** — if Browser Use agents are slow, have pre-cached results that can be "replayed" with real animations

---

## 10. File Structure (Frontend)

```
frontend/
├── app/
│   ├── page.tsx              # Main corkboard view
│   ├── layout.tsx            # Root layout with fonts + providers
│   └── person/[id]/
│       └── page.tsx          # Direct link to dossier (optional)
├── components/
│   ├── Corkboard.tsx         # Pan/zoom canvas with cork texture
│   ├── PersonCard.tsx        # Individual paper card on board
│   ├── ConnectionLine.tsx    # SVG red string between cards
│   ├── DossierView.tsx       # Slide-in detail panel
│   ├── LiveFeed.tsx          # Real-time event sidebar
│   ├── TopBar.tsx            # Header with logo + status
│   ├── StatusBar.tsx         # Bottom status strip
│   ├── TypewriterText.tsx    # Animated text reveal component
│   └── ClassifiedStamp.tsx   # "CLASSIFIED" stamp overlay
├── convex/
│   ├── _generated/           # Auto-generated by Convex
│   ├── schema.ts             # See TECH_DOC.md for schema
│   ├── persons.ts            # Queries: listAll, getById
│   ├── intel.ts              # Queries: recentActivity
│   └── connections.ts        # Queries: listAll, byPerson
├── lib/
│   ├── animations.ts         # Framer Motion variants (from section 5)
│   └── utils.ts              # Board position calculation, etc.
├── public/
│   ├── cork-texture.jpg      # Corkboard background
│   └── fonts/                # If self-hosting fonts
├── styles/
│   └── globals.css           # CSS variables from section 1
├── package.json
├── next.config.js
├── tailwind.config.js
└── tsconfig.json
```

---

## 11. Key Dependencies

```json
{
  "dependencies": {
    "next": "^14",
    "react": "^18",
    "convex": "latest",
    "framer-motion": "^11",
    "@use-gesture/react": "^10",
    "lucide-react": "latest"
  },
  "devDependencies": {
    "tailwindcss": "^3",
    "typescript": "^5",
    "@types/react": "^18"
  }
}
```

---

## 12. Implementation Priority

For the hackathon, build in this order:

1. **Corkboard.tsx** — cork texture + pan/zoom (1 hour)
2. **PersonCard.tsx** — static card with paper texture (1 hour)
3. **Convex integration** — useQuery, real-time updates (30 min)
4. **Card spawn animation** — Framer Motion (30 min)
5. **DossierView.tsx** — slide-in panel with all fields (1 hour)
6. **ConnectionLine.tsx** — SVG strings (30 min)
7. **LiveFeed.tsx** — event stream sidebar (30 min)
8. **TypewriterText.tsx** — character-by-character animation (30 min)
9. **TopBar + StatusBar** — chrome UI (30 min)
10. **Polish** — stamps, sound effects, pre-seeded data (remaining time)

**Total estimated frontend time: ~7 hours**
