# Design System Inspired by VinFast

## 1. Visual Theme & Atmosphere

VinFast's design system embodies modern Vietnamese automotive innovation with a sophisticated, technology-forward aesthetic. The visual language combines vibrant primary blues with deep neutral foundations, creating a professional yet energetic environment that conveys trust, advancement, and sustainability. The design prioritizes clarity and functionality, balancing promotional hero imagery with clean interface elements. Typography emphasizes bold, confident headlines paired with readable body text, while generous whitespace and strategic color blocking guide user attention through product discovery and purchase pathways. The overall atmosphere is premium, dynamic, and forward-thinking—befitting an electric vehicle brand positioning itself as a leader in clean mobility.

**Key Characteristics**
- Bold primary blue (`#007BFF`) for actionable elements and brand recognition
- Deep charcoal (`#3C3C3C`) dominates neutral space, suggesting sophistication
- High contrast between interactive elements and supporting UI
- Clean, modular card layouts with minimal decoration
- Generous spacing supports breathing room and visual hierarchy
- Modern sans-serif typography (Mulish/Noto Sans) conveys tech-forward credibility
- Strategic use of opacity for depth and visual layering
- Emphasis on call-to-action buttons with full-width, high-visibility treatment

## 2. Color Palette & Roles

### Primary
- **Brand Blue** (`#007BFF`): Primary interactive elements, CTAs, links, and brand identity touchpoints (254 uses across the system)
- **Deep Blue** (`#1464F4`): Accent variant for hover states and secondary emphasis (22 uses)

### Accent Colors
- **Azure** (`#007AFF`): Alternative blue accent for cross-device consistency
- **Pale Teal** (`#AACCCC`): Subtle background tinting and light overlays
- **Corporate Blue** (`#2C72C6`): Muted blue for tertiary interactive elements
- **Cyan** (`#17A2B8`): Information and help-related UI

### Interactive
- **Primary CTA** (`#007BFF`): Filled button backgrounds, active states, primary links
- **Secondary Blue** (`#1464F4`): Hover states and focus indicators on blue buttons
- **Ghost Button Text** (`#3C3C3C`): Text-only button styling and secondary actions

### Neutral Scale
- **Charcoal Primary** (`#3C3C3C`): Dominant text color, primary interface elements (582 uses)
- **Near Black** (`#1F2125`): Heading text and high-contrast elements (109 uses)
- **Dark Neutral** (`#151515`): Deep shadows and extreme contrast overlays
- **Medium Gray** (`#707070`): Tertiary text and disabled states
- **Light Gray** (`#D9D9D9`): Subtle dividers and low-emphasis elements
- **White** (`#FFFFFF`): Primary background and text on dark surfaces (42 uses)
- **Off-White** (`#F8F9FA`): Light section backgrounds and card surfaces

### Surface & Borders
- **Card Background Light** (`#F8F9FA`): Light surface and container backgrounds
- **Border Gray** (`#D9D9D9`): Subtle borders on input fields and card edges
- **Subtle Border** (`#D9E1E2`): Very light borders for minimal visual separation
- **Input Border** (`#707070`): Standard form field borders

### Semantic / Status
- **Danger** (`#DC3545`): Error messages, destructive actions, and alert states
- **Warning** (`#FFC107`): Caution messages and non-critical alerts
- **Success** (`#28A745`): Confirmation messages and completed states

## 3. Typography Rules

### Font Family
**Primary:** Mulish (via system defaults) with fallback: `Mulish, 'Noto Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`

**Secondary:** Noto Sans Vietnamese (https://fonts.googleapis.com/css?family=Noto+Sans:300,400,600,700&display=swap&subset=vietnamese) for all text rendering and localization support.

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|------|------|------|--------|-------------|---|---|
| Display / Hero | Mulish | 32px | 700 | 36px | normal | Large hero headlines, section titles |
| Heading 1 | Mulish | 28px | 600 | 28px | normal | Primary page headings |
| Heading 2 | Mulish | 24px | 600 | 36px | normal | Section subheadings and card titles |
| Heading 3 | Mulish | 16px | 700 | 20.8px | normal | Tertiary headings and emphasis text |
| Body Primary | Mulish | 16px | 400 | 24px | normal | Standard paragraph text and body copy |
| Body Bold | Mulish | 16px | 600 | 24px | normal | Emphasized body text and input values |
| Button Text | Mulish | 20px | 600 | 24px | normal | Primary CTA and action button labels |
| Label / Form | Mulish | 14px | 400 | 20px | normal | Form labels, captions, and helpers |
| Caption | Mulish | 16px | 400 | 24px | normal | Tertiary text, fine print, metadata |
| Code / Monospace | Mulish | 12.8px | 400 | normal | normal | Price displays, technical info |

### Principles
- Use **700 weight** for high-emphasis headlines to command visual attention
- Employ **600 weight** for secondary headings and bold body text, creating clear hierarchical separation
- Reserve **400 weight** for extended reading—body copy, labels, and captions
- Maintain **24px line height** for body text to ensure comfortable readability across screen sizes
- Apply **normal letter spacing** throughout; tracking adjustments are intentionally minimal to maintain modern, tight typographic appearance
- Scale responsively: on mobile, reduce heading sizes by 20–30% while maintaining proportional hierarchy
- Always pair headlines with adequate whitespace below to establish visual breathing room

## 4. Component Stylings

### Buttons

#### Primary Button (Filled)
- **Background:** `#007BFF`
- **Text Color:** `#FFFFFF`
- **Padding:** `12px 24px`
- **Font Size:** `16px`
- **Font Weight:** `600`
- **Border Radius:** `4px`
- **Border:** `0px none`
- **Height:** `48px`
- **Width:** `auto` (full-width on mobile)
- **Line Height:** `24px`
- **Hover State:** Background `#1464F4`, text `#FFFFFF`
- **Active State:** Background `#0056CC`, text `#FFFFFF`
- **Disabled State:** Background `rgba(0, 123, 255, 0.5)`, text `rgba(255, 255, 255, 0.6)`, opacity `0.5`

#### Primary Large Button (Hero CTA)
- **Background:** `#007BFF`
- **Text Color:** `#FFFFFF`
- **Padding:** `12px 32px`
- **Font Size:** `20px`
- **Font Weight:** `600`
- **Border Radius:** `4px`
- **Border:** `0px none`
- **Height:** `auto`
- **Width:** `100%`
- **Line Height:** `24px`
- **Hover State:** Background `#1464F4`, text `#FFFFFF`, box-shadow `rgba(0, 123, 255, 0.3) 0px 4px 12px 0px`
- **Active State:** Background `#0056CC`

#### Secondary Button (Outlined)
- **Background:** `#FFFFFF`
- **Text Color:** `#007BFF`
- **Padding:** `11px 16px`
- **Font Size:** `16px`
- **Font Weight:** `600`
- **Border Radius:** `4px`
- **Border:** `1px solid #007BFF`
- **Height:** `auto`
- **Width:** `auto`
- **Line Height:** `24px`
- **Hover State:** Background `rgba(0, 123, 255, 0.05)`, text `#1464F4`, border `1px solid #1464F4`

#### Ghost Button (Light Background)
- **Background:** `rgba(217, 217, 217, 0.4)` (Light Gray with 40% opacity)
- **Text Color:** `#3C3C3C`
- **Padding:** `0px`
- **Font Size:** `16px`
- **Font Weight:** `400`
- **Border Radius:** `8px 0px 0px 8px` or `0px` (variant dependent)
- **Border:** `0px none`
- **Height:** `68px`
- **Width:** `136px`
- **Line Height:** `24px`
- **Hover State:** Background `rgba(217, 217, 217, 0.6)`, text `#1F2125`

#### Navigation Button
- **Background:** `rgba(0, 0, 0, 0)` (Transparent)
- **Text Color:** `#3C3C3C`
- **Padding:** `0px`
- **Font Size:** `16px`
- **Font Weight:** `400`
- **Border Radius:** `5px`
- **Border:** `0px none`
- **Height:** `25px`
- **Width:** `auto`
- **Line Height:** `24px`
- **Hover State:** Background `rgba(0, 123, 255, 0.1)`, text `#007BFF`
- **Active State:** Text `#007BFF`, border-bottom `2px solid #007BFF`

### Cards & Containers

#### Standard Card
- **Background:** `#FFFFFF` or `#F8F9FA`
- **Border:** `0px none` or `1px solid #D9D9D9`
- **Border Radius:** `10px`
- **Padding:** `20px`
- **Box Shadow:** `rgba(0, 0, 0, 0.16) 0px 3px 6px 0px`
- **Width:** `220px` (default grid unit)
- **Height:** `auto`

#### Product Card
- **Background:** `#FFFFFF`
- **Border:** `1px solid #D9E1E2`
- **Border Radius:** `10px`
- **Padding:** `16px`
- **Box Shadow:** `rgba(0, 0, 0, 0.16) 0px 3px 6px 0px` on hover
- **Transition:** All properties `0.3s ease`
- **Hover State:** Transform `translateY(-4px)`, box-shadow `rgba(0, 0, 255, 0.2) 0px 8px 16px 0px`

#### Hero Container
- **Background:** Linear gradient from light blue (`#E8F4FF`) to dark navy (`#0A1C3A`)
- **Padding:** `48px 32px` (desktop), `32px 16px` (mobile)
- **Border Radius:** `0px`
- **Text Color:** `#FFFFFF` (on hero overlay)

### Inputs & Forms

#### Text Input (Standard)
- **Background:** `#FFFFFF`
- **Text Color:** `#3C3C3C`
- **Border:** `1px solid #707070`
- **Border Radius:** `0px`
- **Padding:** `16px`
- **Font Size:** `16px`
- **Font Weight:** `600`
- **Height:** `48px`
- **Width:** `100%`
- **Line Height:** `24px`
- **Focus State:** Border `1px solid #007BFF`, box-shadow `0px 0px 0px 3px rgba(0, 123, 255, 0.2)`
- **Placeholder Text:** Color `rgba(112, 112, 112, 0.6)`, weight `400`

#### Search Input (Rounded)
- **Background:** `#FFFFFF`
- **Text Color:** `#3C3C3C`
- **Border:** `1px solid #707070`
- **Border Radius:** `50px`
- **Padding:** `6px 35px 6px 15px`
- **Font Size:** `12.8px`
- **Font Weight:** `400`
- **Height:** `31px`
- **Width:** `100%`
- **Line Height:** `normal`
- **Focus State:** Border `1px solid #007BFF`, background `#FFFFFF`

#### Form Label
- **Text Color:** `#1F2125`
- **Font Size:** `14px`
- **Font Weight:** `400`
- **Line Height:** `20px`
- **Margin Bottom:** `8px`
- **Display:** `block`

#### Disabled Input
- **Background:** `#F8F9FA`
- **Text Color:** `rgba(60, 60, 60, 0.5)`
- **Border:** `1px solid #D9D9D9`
- **Opacity:** `0.6`
- **Cursor:** `not-allowed`

### Navigation

#### Top Navigation Bar
- **Background:** `#FFFFFF`
- **Height:** `64px`
- **Padding:** `0px 32px`
- **Border Bottom:** `1px solid #E8E8E8`
- **Box Shadow:** `rgba(0, 0, 0, 0.08) 0px 2px 4px 0px`
- **Z-index:** `999`
- **Position:** `sticky`

#### Navigation Link
- **Text Color:** `#3C3C3C`
- **Font Size:** `16px`
- **Font Weight:** `400`
- **Padding:** `12px 16px`
- **Border Radius:** `5px`
- **Hover State:** Background `rgba(0, 123, 255, 0.1)`, text `#007BFF`
- **Active State:** Text `#007BFF`, border-bottom `2px solid #007BFF`

#### Hamburger Menu (Mobile)
- **Width:** `24px`
- **Height:** `24px`
- **Padding:** `8px`
- **Background:** `transparent`
- **Border:** `none`
- **Cursor:** `pointer`
- **Z-index:** `1000`

### Links

#### Text Link (Default)
- **Text Color:** `#007BFF`
- **Font Size:** `16px`
- **Font Weight:** `400`
- **Line Height:** `24px`
- **Background:** `transparent`
- **Border:** `none`
- **Padding:** `0px`
- **Text Decoration:** `none`
- **Hover State:** Text Color `#1464F4`, text-decoration `underline`
- **Active State:** Text Color `#0056CC`

#### Link with Icon
- **Display:** `inline-flex`
- **Gap:** `8px`
- **Align Items:** `center`
- **Hover State:** Icon color matches text link hover state

### Badges (Semantic Status)

#### Success Badge
- **Background:** `rgba(40, 167, 69, 0.1)`
- **Text Color:** `#28A745`
- **Border:** `1px solid #28A745`
- **Padding:** `4px 12px`
- **Border Radius:** `20px`
- **Font Size:** `12px`
- **Font Weight:** `600`

#### Warning Badge
- **Background:** `rgba(255, 193, 7, 0.1)`
- **Text Color:** `#FFC107`
- **Border:** `1px solid #FFC107`
- **Padding:** `4px 12px`
- **Border Radius:** `20px`
- **Font Size:** `12px`
- **Font Weight:** `600`

#### Danger Badge
- **Background:** `rgba(220, 53, 69, 0.1)`
- **Text Color:** `#DC3545`
- **Border:** `1px solid #DC3545`
- **Padding:** `4px 12px`
- **Border Radius:** `20px`
- **Font Size:** `12px`
- **Font Weight:** `600`

## 5. Layout Principles

### Spacing System

VinFast's spacing system uses an 4px base unit with a modular scale for consistent, predictable layouts.

- **4px:** Micro spacing for icon-text pairs, tight component spacing
- **8px:** Small padding and gaps between small elements
- **12px:** Compact spacing between related items
- **16px:** Standard padding inside components (buttons, inputs, cards)
- **20px:** Gap between component groups, section breaks
- **24px:** Comfortable spacing between sections
- **32px:** Medium section padding and container margins
- **48px:** Large section padding for primary content areas
- **64px:** Hero section gaps and major layout breaks
- **96px:** Extra-large spacing between major page sections
- **136px:** Maximum spacing between full-width sections on desktop

**Usage Context:**
- **Internal Component Padding:** 16px (inputs, buttons, cards)
- **Between Components:** 12px–20px (tight grouping)
- **Section Padding:** 32px–48px (horizontal), 64px (vertical)
- **Hero Sections:** 96px (vertical), 48px (horizontal)
- **Page Margins:** 32px (tablet), 48px (desktop)

### Grid & Container

- **Max Width:** `1400px` (desktop)
- **Columns:** 12-column flexible grid
- **Gutter:** `20px` (desktop), `12px` (tablet), `8px` (mobile)
- **Container Padding:** `32px` (desktop), `20px` (tablet), `16px` (mobile)
- **Min Width:** `320px` (mobile), fully responsive below

**Section Patterns:**
- Full-width hero sections with centered content overlay
- Two-column layouts for product showcase and specifications
- Three-column card grids for related items
- Single-column layouts for forms and detail pages
- Sticky header navigation with flexible content flow below

### Whitespace Philosophy

Generous whitespace is a core design principle, breathing room between elements reduces cognitive load and emphasizes hierarchy. Content breathing room:
- Headings benefit from 16–24px bottom margin before related copy
- Body paragraphs maintain 12–16px bottom margin
- Card interiors use 16–20px padding to frame content without crowding
- Section transitions employ 48–96px vertical spacing for clear separation

This approach prevents visual overwhelm and guides user focus toward actionable elements.

### Border Radius Scale

- **0px:** Form inputs (standard), modal backdrops, full-width sections
- **4px:** Default button corners, small interactive elements
- **4.8px:** Modal dialog boxes, subtle rounded containers
- **5px:** Navigation elements, tab borders
- **10px:** Card containers, product showcase panels
- **50px:** Search inputs, fully rounded pill-button styling

### Border Widths

- **Thin (1px):** Default borders on form inputs, card edges, subtle dividers
- **Medium (2px):** Active state underlines on navigation, emphasis borders
- **Thick (3px):** Modal shadow definition and high-contrast overlays (via box-shadow)

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Base | No shadow, flat surface | Buttons, text, primary UI |
| Raised | `rgba(0, 0, 0, 0.16) 0px 3px 6px 0px` | Cards, containers, dropdown menus |
| Elevated | `rgba(0, 0, 0, 0.3) 0px 8px 16px 0px` | Modals, overlays, hover states on cards |
| Modal | `rgba(0, 0, 0, 0.5) 0px 3px 8px 0px` | Dialog boxes, top-layer UI elements |

**Shadow Philosophy:**

VinFast employs a subtle, realistic shadow system that provides depth without visual noise. Shadows follow a consistent offset pattern (0px horizontal, 3–8px vertical) with moderate blur and opacity. This creates a clean, layered effect suggesting elevation and interactivity. Shadows intensify on hover to signal engagement. Modal and overlay shadows are darker and more pronounced, establishing clear visual hierarchy and drawing focus to critical UI.

### Opacity Levels

- **3% (0.03):** Barely perceptible background tints and borders
- **20% (0.20):** Light interactive state backgrounds (hover, focus)
- **40% (0.40):** Medium opacity overlays and disabled state backgrounds
- **50% (0.50):** Strong visual separation, semi-transparent overlays
- **97% (0.97):** Near-opaque state for high-contrast disabled or inactive elements

**Application:**
- Disabled input backgrounds: `rgba(248, 249, 250, 0.6)` opacity
- Hover state backgrounds: `rgba(0, 123, 255, 0.1)` or `0.05`
- Modal backdrops: `rgba(0, 0, 0, 0.5)` opacity
- Focus highlights: `rgba(0, 123, 255, 0.2)` box-shadow

### Z-index / Layering

- **Base Layer (1–3):** Page content, cards, standard components
- **Dropdown Layer (10):** Dropdowns, popovers, context menus
- **Sticky Layer (99):** Sticky headers, navigation bars
- **Sticky High (998):** Persistent floating elements, back-to-top buttons
- **Modal Layer (999):** Modal dialogs, full-page overlays
- **Top Layer (1000):** Toast notifications, alerts

**Z-index Strategy:** Strictly hierarchical to prevent stacking conflicts. Reserve 999 for modals as the highest standard layer; exceed only for system-critical notifications.

## 7. Do's and Don'ts

### Do
- **Use `#007BFF` for all primary actions** — buttons, links, and interactive states. This builds brand recognition and consistency.
- **Pair headings with adequate whitespace** — minimum 16px below headings before body text begins. This improves readability.
- **Apply hover states to all interactive elements** — shift color or add subtle box-shadow to signal engagement.
- **Use the 4px base unit for all spacing** — maintain alignment and consistency across all layouts.
- **Employ Mulish/Noto Sans exclusively** — this ensures Vietnamese character support and modern aesthetic.
- **Apply shadows only to elevated containers** (cards, modals) — reserve shadows for depth, not decoration.
- **Make CTAs full-width on mobile** — increases touch target size and conversion intent.
- **Use semantic color for status badges** — green for success, orange/yellow for warning, red for danger.
- **Test form inputs with placeholder text** — ensure sufficient contrast and clarity.
- **Nest modals within the 999 z-index layer** — prevents layering bugs and ensures visibility.

### Don't
- **Mix font families** — avoid system fonts or serif typefaces; Mulish/Noto Sans is mandatory.
- **Use colors outside the defined palette** — respect the 19-color system; custom colors break consistency.
- **Apply shadows to flat elements** — shadows should indicate elevation, not decoration.
- **Overcrowd whitespace** — maintain breathing room; cramped layouts reduce usability.
- **Reduce touch targets below 44px** — buttons and interactive elements must be at least 44×44px on mobile.
- **Underline non-linked text** — underlines signal links; reserve for text links only.
- **Mix opacity values** — use the defined 0.03, 0.20, 0.40, 0.50, 0.97 scale exclusively.
- **Create custom border radii** — use only 0px, 4px, 4.8px, 5px, 10px, 50px.
- **Apply multiple shadows** — use the defined elevation levels; avoid stacked or custom shadows.
- **Disable form inputs without visual feedback** — ensure disabled inputs are clearly distinct (opacity, color change).

## 8. Responsive Behavior

### Breakpoints

| Breakpoint | Width | Key Changes |
|---|---|---|
| Mobile | 320px–767px | Single column, full-width components, 16px padding, 12px gaps, 14px headings |
| Tablet | 768px–1023px | Two columns, 20px padding, 16px gaps, 18px headings |
| Desktop | 1024px–1399px | Three columns, 32px padding, 20px gaps, 24px headings |
| Large Desktop | 1400px+ | Full-width max 1400px, 48px padding, 24px gaps, 32px headings |

### Touch Targets

- **Minimum touch target:** `44px × 44px` on mobile and tablet
- **Button height:** `48px` (desktop and mobile)
- **Link touch area:** `32px × 32px` minimum
- **Form field height:** `48px` for text inputs, `31px` for search inputs
- **Icon size:** `24px` with `8px` padding for sufficient touch area
- **Spacing between touch targets:** `12px` minimum to prevent accidental activation

### Collapsing Strategy

**Mobile (320px–767px):**
- Stack all multi-column layouts to single column
- Convert sidebar navigation to hamburger menu
- Full-width cards and containers (16px margin)
- Hero sections reduce to 1:1 or 16:9 aspect ratio
- Buttons full-width within forms
- Hide secondary navigation items; show only primary actions
- Reduce heading sizes: h1 24px, h2 18px, h3 14px

**Tablet (768px–1023px):**
- Two-column layouts, grid 6 columns
- Navigation converts to horizontal compact menu
- Cards arrange 2 per row
- Hero sections maintain 16:9 ratio
- Button widths auto (not full-width)
- Heading sizes: h1 26px, h2 20px, h3 16px

**Desktop (1024px+):**
- Full three-column layouts, 12-column grid
- Navigation full horizontal bar
- Cards arrange 3–4 per row
- Hero sections full-width, optimized imagery
- Buttons auto-width
- Full heading sizes per hierarchy table
- Max container width 1400px, centered

**Flex & Grid Strategy:**
- Use `flex-wrap: wrap` for card grids; adjust gap and item width at breakpoints
- Use CSS Grid with `auto-fit` or `auto-fill` for responsive column counts
- Apply `max-width: 100%` to images and embedded content
- Use `clamp()` for fluid typography: `font-size: clamp(14px, 3vw, 32px)`

## 9. Agent Prompt Guide

### Quick Color Reference

- **Primary CTA:** Brand Blue (`#007BFF`)
- **CTA Hover:** Deep Blue (`#1464F4`)
- **Background (Light):** Off-White (`#F8F9FA`)
- **Background (Dark):** Charcoal Primary (`#3C3C3C`)
- **Heading Text:** Near Black (`#1F2125`)
- **Body Text:** Charcoal Primary (`#3C3C3C`)
- **Link Text:** Brand Blue (`#007BFF`)
- **Border:** Border Gray (`#D9D9D9`) or Subtle Border (`#D9E1E2`)
- **Success Status:** Success Green (`#28A745`)
- **Warning Status:** Warning Amber (`#FFC107`)
- **Error Status:** Danger Red (`#DC3545`)

### Iteration Guide

1. **Always import Mulish/Noto Sans fonts** — use the Google Fonts CDN link provided in Font Family section; fallback to system sans-serif.

2. **Apply brand blue (`#007BFF`) to all primary buttons** — never use alternate colors for main CTAs; use `#1464F4` only on hover/active states.

3. **Use the 4px spacing scale exclusively** — all margin, padding, and gap values must be multiples of 4px (4, 8, 12, 16, 20, 24, 32, 48, 64, 96, 136).

4. **Maintain minimum 44px touch targets** on mobile and tablet; desktop buttons can be 36–40px if necessary.

5. **Apply box-shadow depth only to cards and modals** — use `rgba(0, 0, 0, 0.16) 0px 3px 6px 0px` for raised elements, `rgba(0, 0, 0, 0.5) 0px 3px 8px 0px` for modals.

6. **Use the defined border radius values only** — 0px (flat), 4px (buttons/inputs), 5px (nav), 10px (cards), 50px (search inputs).

7. **Render headings in the specified hierarchy weights** — h1/h2 at 600–700 weight, body text at 400 weight, labels at 400 weight.

8. **Structure responsive breakpoints at 320px (mobile), 768px (tablet), 1024px (desktop)** — collapse columns, adjust padding, hide secondary UI accordingly.

9. **Reserve z-index 999 for modals, 998 for sticky elements, 99 for dropdowns** — never exceed 1000 unless for system alerts.

10. **Implement proper semantic color badges** — green for success, amber for warning, red for error; use defined opacity levels (0.1 background + border, solid text color).