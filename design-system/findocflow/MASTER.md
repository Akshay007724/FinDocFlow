# Design System Master File — FinDocFlow

> **LOGIC:** When building a specific page, first check `design-system/findocflow/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** FinDocFlow
**Category:** Financial Dashboard (Dark OLED)
**Target user:** Equity research analysts, quant teams
**Design pattern:** Real-Time Operations Dashboard

---

## Color Palette — Dark OLED (Financial Dashboard #3 from colors.csv)

All tokens as CSS variables on `:root`. Use Tailwind `theme.extend.colors` mapping.

| Role | Hex | Tailwind key | Usage |
|------|-----|--------------|-------|
| `--bg` | `#020617` | `bg-background` | App background (deep OLED) |
| `--surface` | `#0E1223` | `bg-card` | Cards, side panels |
| `--surface-2` | `#1A1E2F` | `bg-muted` | Inputs, secondary surfaces |
| `--border` | `#334155` | `border-border` | Dividers, card borders |
| `--fg` | `#F8FAFC` | `text-foreground` | Primary text (≥7:1 contrast) |
| `--fg-muted` | `#94A3B8` | `text-muted-foreground` | Secondary text (≥4.5:1) |
| `--primary` | `#2563EB` | `bg-primary` | Primary buttons, active tabs |
| `--primary-fg` | `#FFFFFF` | `text-primary-foreground` | Text on primary |
| `--accent` | `#22C55E` | `text-accent / bg-accent` | Positive values, success, up-ticks |
| `--warning` | `#F59E0B` | `text-warning` | Caveats, medium confidence |
| `--destructive` | `#EF4444` | `text-destructive` | Errors, down-ticks, DLQ |
| `--ring` | `#2563EB` | `ring-primary` | Keyboard focus ring (2px solid) |

**Contrast verified:** `#F8FAFC` on `#020617` = 17.6:1 (AAA). `#94A3B8` on `#020617` = 7.9:1 (AAA).

---

## Typography — Financial Trust + Tabular

| Role | Font | Weights | Use |
|------|------|---------|-----|
| Headings & UI | **IBM Plex Sans** | 400 / 500 / 600 / 700 | All display + body text |
| Numerical data | **Fira Code** | 400 / 500 | Tables of figures, KPI values, timestamps |

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=Fira+Code:wght@400;500;600&display=swap');
```

**Type scale (Tailwind config):**
```
text-xs   12px / line 16px   labels, captions
text-sm   14px / line 20px   body secondary
text-base 16px / line 24px   body primary (mobile min)
text-lg   18px / line 28px   card titles
text-xl   20px / line 28px   section headings
text-2xl  24px / line 32px   page titles
text-3xl  30px / line 36px   dashboard hero
text-4xl  36px / line 40px   landing hero
```

All numeric table cells: `font-mono tabular-nums` (Fira Code).

---

## Spacing & Radii

4px base scale. Tailwind defaults are kept; custom additions:

| Token | Value | Usage |
|-------|-------|-------|
| `space-xs` | 4px | Tight icon/text gaps |
| `space-sm` | 8px | Button padding Y, inline gaps |
| `space-md` | 16px | Card inner padding, form gaps |
| `space-lg` | 24px | Section padding, card outer margin |
| `space-xl` | 32px | Page gutter on desktop |
| `space-2xl` | 48px | Section separation |

**Radii:** `rounded-md` 6px (buttons, inputs) · `rounded-lg` 10px (cards) · `rounded-xl` 14px (modals) · `rounded-full` for chips.

---

## Elevation (dark mode)

Use **borders + subtle inner glow** over shadows (shadows are invisible on pure black).

| Level | Tailwind | Purpose |
|-------|----------|---------|
| `elev-0` | `border border-border/50` | Default card surface |
| `elev-1` | `border border-border bg-card` | Raised card |
| `elev-2` | `border border-border bg-card shadow-[0_0_0_1px_rgba(37,99,235,0.2)]` | Active/hover card |
| `elev-modal` | `border border-border bg-card shadow-[0_20px_50px_-12px_rgba(0,0,0,0.8)]` | Modal, popover |

Hover: ring glow `ring-1 ring-primary/30`, never transform that shifts layout.

---

## Motion Tokens

| Token | Duration | Easing | Use |
|-------|----------|--------|-----|
| `motion-fast` | 120ms | `ease-out` | Hover tints, focus rings |
| `motion-base` | 200ms | `cubic-bezier(0.2, 0, 0, 1)` (MD emphasized) | State transitions |
| `motion-slow` | 320ms | `cubic-bezier(0.2, 0, 0, 1)` | Modal/sheet enter |
| Exit durations = 70% of enter. |

All motion gated on `@media (prefers-reduced-motion: reduce)` → zero duration.

---

## Component Specs

### Buttons

```tsx
// Primary
<button className="h-10 px-4 rounded-md bg-primary text-primary-foreground font-medium
                   transition-[background,box-shadow] duration-200
                   hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background
                   disabled:opacity-50 disabled:cursor-not-allowed" />

// Secondary (outline)
<button className="h-10 px-4 rounded-md border border-border bg-transparent text-foreground
                   hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring" />

// Destructive
<button className="h-10 px-4 rounded-md bg-destructive/10 text-destructive border border-destructive/30
                   hover:bg-destructive/20" />
```

All buttons: min 44×44 touch target (use padding, not just height on mobile).

### Cards

```tsx
<div className="rounded-lg border border-border bg-card p-6 transition-colors duration-200
                hover:border-border/80 hover:ring-1 hover:ring-primary/20" />
```

### Inputs

```tsx
<input className="h-10 w-full rounded-md border border-border bg-muted px-3 text-sm
                  text-foreground placeholder:text-muted-foreground
                  focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30" />
```

### KPI Tile

```tsx
<div className="rounded-lg border border-border bg-card p-5">
  <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Docs ingested (24h)</div>
  <div className="mt-2 font-mono text-3xl tabular-nums text-foreground">1,284</div>
  <div className="mt-1 flex items-center gap-1 text-xs text-accent">
    <ArrowUpRight className="h-3 w-3" /> +12.4% vs prev 24h
  </div>
</div>
```

### Status Pill (for document states)

```
pending     → bg-warning/15    text-warning      border-warning/30
processing  → bg-primary/15    text-primary      border-primary/30   + pulsing dot
done        → bg-accent/15     text-accent       border-accent/30
failed      → bg-destructive/15 text-destructive border-destructive/30
```

---

## Iconography

**Use Lucide React only.** Stroke 1.5. Size scale: `h-4 w-4` (inline), `h-5 w-5` (buttons), `h-6 w-6` (headers), `h-8 w-8` (empty states).

**No emojis anywhere in UI chrome.** Emojis only allowed inside LLM output content (sanitized first).

---

## Chart System (Recharts)

| Data shape | Chart | Notes |
|-----------|-------|-------|
| Time-series (throughput, latency) | Line + Area fill 10% | Single primary color, pattern dash per series if >1 |
| Confidence distribution | Horizontal bar | Sorted desc, value labels always visible |
| KPI vs target | Bullet chart | `#FFCDD2`/`#FFF9C4`/`#C8E6C9` range bands with dark overlay |
| Pipeline live throughput | Streaming area (Canvas) | Must include Pause/Resume button |

All charts ship a collapsible "View data table" for screen readers.

---

## Layout System

| Breakpoint | Width | Layout |
|-----------|-------|--------|
| `sm` | ≥640px | Single column, bottom nav |
| `md` | ≥768px | Sidebar collapses to icons |
| `lg` | ≥1024px | Sidebar expanded, 2-column content |
| `xl` | ≥1280px | 3-column content, max-w `7xl` |

**Shell:** left sidebar (nav) · top bar (breadcrumb + search + user) · main scroll region. Sidebar can collapse to 56px icon-only on md.

**Keyboard shortcuts:**
- `⌘/Ctrl + K` → Command palette (fuzzy nav + actions)
- `⌘/Ctrl + Enter` → Submit chat
- `g d` → Dashboard, `g l` → Library, `g r` → Reports, `g c` → Chat (vim-style leader nav)

---

## Pages

1. **Dashboard** — Hero KPIs (4 tiles), pipeline live chart, recent documents table, system health grid.
2. **Library** — Filterable table, upload drop-zone, bulk actions, status pills.
3. **Document detail** — Split view: page viewer (PDF.js) left, extracted entities/tables right, citation linking between them.
4. **Report generator** — Doc multi-select → section chip grid → Generate → per-section streaming status (`st.status` equivalent via SSE).
5. **Chat** — Full-height layout, message stream with page citations, analyst focus selector, `/` command for doc reference.
6. **Knowledge graph** — Force-directed view of Neo4j entities (react-force-graph-2d), filter by company/period.
7. **Pipeline monitor** — Kafka lag, DLQ counts, service health, Grafana iframe embed (link-out to full dashboards).

---

## Accessibility (non-negotiable)

- All interactive elements ≥44×44 touch target.
- Focus-visible rings on every keyboard-reachable element (2px `ring-primary`).
- `aria-label` on every icon-only button.
- Color-not-only: every status uses icon + text + color.
- `prefers-reduced-motion` honored by disabling all duration > 0ms.
- Table sort uses `aria-sort`; live regions (`aria-live="polite"`) on toasts and streaming chat.
- Dynamic type: base 16px, scales via rem; no `max-width` traps below 40ch line length.

---

## Anti-patterns (do NOT ship)

- ❌ Emojis as structural icons (use Lucide SVG).
- ❌ Layout-shifting hovers (translate/scale on parent containers).
- ❌ Placeholder-only labels.
- ❌ `*` CORS on any FastAPI backend.
- ❌ Color-alone semantic indicators (green = good needs ✓ icon + "Succeeded" text).
- ❌ Instant state changes (≥120ms transition on every state swap).
- ❌ Hover-only tooltips with critical info (must be keyboard-reachable).
- ❌ Pie charts with >5 slices.

---

## Pre-delivery Checklist

- [ ] All interactive elements have visible focus rings
- [ ] All text meets 4.5:1 contrast on `#020617`
- [ ] No emojis as icons
- [ ] Responsive at 375 / 768 / 1024 / 1440
- [ ] `prefers-reduced-motion` disables non-essential motion
- [ ] Command palette (`⌘K`) opens and navigates
- [ ] Tables support keyboard sort + screen reader announcement
- [ ] Loading states use skeletons (not blank spinners) for ≥300ms
- [ ] Error states surface retry action, not just dismissal
- [ ] Charts include a keyboard-accessible data table alternative
