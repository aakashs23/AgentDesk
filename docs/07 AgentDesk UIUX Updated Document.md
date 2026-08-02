# Master UI/UX Design Specification: AgentDesk

## 1. Product Vision
AgentDesk aims to be the most frictionless, high-performance ticket management and support platform available. The interface is engineered to eliminate cognitive overload, prioritizing speed, data density, and immediate clarity. It empowers support teams to operate at peak efficiency without fighting the software.

## 2. Brand Identity
The brand identity is rooted in a **premium, minimalistic aesthetic**. It avoids playful or extraneous decorative elements, projecting absolute professional competence and reliability. The visual brand relies on stark contrast, perfect alignment, and purposeful use of our primary blue to guide user focus. 

## 3. Design Language
The design language is defined by **Engineered Reduction**. Every component must serve a distinct functional purpose. We rely on spatial tension, exact typography, and subtle volumetric lighting (via shadows) to create hierarchy. All graphic assets must be extremely minimal, vector-based, and geometrically precise. 

## 4. Layout Rules
*   **Containment:** The main application operates within a fluid but constrained container.
*   **Max-Width:** The central dashboard content wrapper is capped at exactly `1152px` to ensure optimal reading line lengths (60-80 characters) for ticket descriptions and articles.
*   **Alignment:** Strict left-alignment for all textual content; center-alignment is reserved exclusively for empty states and isolated modals.

## 5. Grid System
A rigid **4pt baseline grid** governs all spatial relationships. 
*   **Columns:** 12-column fluid grid for dashboard widgets.
*   **Gutters:** `24px` exact gutter width between dashboard columns.
*   **Spacing Tokens:**
    *   `space-1`: 4px
    *   `space-2`: 8px
    *   `space-3`: 12px
    *   `space-4`: 16px
    *   `space-6`: 24px
    *   `space-8`: 32px
    *   `space-12`: 48px
    *   `space-16`: 64px

## 6. Sidebar
*   **Width:** Fixed at `260px`.
*   **Surface:** `#F9FAFB` (blends seamlessly with the main canvas).
*   **Behavior:** Persists on desktop. Collapses into a drawer on screens under `1024px`.
*   **Items:** `32px` height, `8px` border-radius. Active state applies a `#0066FF` left border (3px width) or subtle `rgba(0, 102, 255, 0.08)` background fill.

## 7. Header
*   **Height:** Fixed at `64px`.
*   **Surface:** `#FFFFFF` with a bottom border of `1px solid #F3F4F6`.
*   **Content:** Contains breadcrumbs, global search/command trigger, and user profile avatar (`32x32px`, `9999px` radius).
*   **Behavior:** Sticky top, utilizing a glass effect (`backdrop-filter: blur(12px)`) if scrolling content passes beneath it.

## 8. Dashboard
*   **Padding:** `32px` top/bottom, `32px` left/right.
*   **Widget Gap:** `24px` standard gap between analytical cards.
*   **Hierarchy:** Key metrics (e.g., Open Tickets) occupy the top row, followed by wider charts, and ending with list views (recent tickets).

## 9. Tables
*   **Row Height:** `48px` (compact), `64px` (comfortable).
*   **Header:** `12px` font size, `500` weight, uppercase, `#6B7280` text. Sticky top.
*   **Dividers:** `1px solid #F3F4F6` at the bottom of each row.
*   **Interactions:** Entire row is clickable. Hover state shifts row background to `#F3F4F6`. Text links within rows use `#0066FF`.

## 10. Forms
*   **Label:** `13px`, `500` weight, `#111827`, placed `8px` above the input.
*   **Widths:** Constrain input widths based on expected data (e.g., zip codes should not span 100% width).
*   **Layout:** Use single-column layouts for complex settings, avoiding multi-column forms that disrupt vertical scanning.

## 11. Buttons
*   **Height:** `36px` (Standard), `44px` (Large/Primary).
*   **Border Radius:** `8px` exact.
*   **Primary:** Background `#0066FF`, Text `#FFFFFF`. Hover: `#0052CC`.
*   **Secondary:** Background `transparent`, Border `1px solid #E5E7EB`, Text `#111827`. Hover: `#F9FAFB`.
*   **Danger:** Background `#EF4444`, Text `#FFFFFF`.

## 12. Inputs
*   **Surface:** `#F9FAFB`.
*   **Border:** `1px solid transparent`.
*   **Text:** `#111827`, `14px`.
*   **Padding:** `8px` vertical, `12px` horizontal.
*   **Focus State (Crucial):** Background transitions to `#FFFFFF`, border transitions to `#0066FF`, and applies `box-shadow: 0 0 0 3px rgba(0, 102, 255, 0.15)`.

## 13. Cards
*   **Surface:** `#FFFFFF`.
*   **Border:** None.
*   **Radius:** `16px`.
*   **Elevation:** `box-shadow: 0px 4px 6px -1px rgba(0, 0, 0, 0.05), 0px 2px 4px -1px rgba(0, 0, 0, 0.03)`.
*   **Padding:** `24px` internal padding.

## 14. Modals
*   **Backdrop:** `rgba(17, 24, 39, 0.6)` with `backdrop-filter: blur(4px)`.
*   **Surface:** `#FFFFFF`, `16px` radius.
*   **Elevation:** Level 3 (`box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25)`).
*   **Animation:** Scale in from `0.95` to `1.0`, opacity `0` to `1` over `200ms cubic-bezier(0.16, 1, 0.3, 1)`.
*   **Structure:** Distinct header (with close 'X'), scrollable body, and fixed footer for CTA buttons.

## 15. Drawers
*   **Placement:** Slide in from the right edge.
*   **Width:** `400px` (standard forms), `600px` (complex ticket views).
*   **Animation:** Translate X from `100%` to `0%` over `300ms cubic-bezier(0.2, 0.8, 0.2, 1)`.

## 16. Notifications (Toasts)
*   **Position:** Bottom-right corner, `24px` offset.
*   **Structure:** `320px` width, `#FFFFFF` background, Elevation 3.
*   **Indicator:** `4px` left border indicating status (Blue for info, Green for success, Red for error).
*   **Timeout:** Auto-dismiss after `4000ms`.

## 17. Search
*   **Placement:** Global search in header.
*   **Style:** `40px` height, `#F3F4F6` background, `9999px` pill radius.
*   **Behavior:** Acts as a trigger for the Command Palette rather than a standard inline input.

## 18. Command Palette
*   **Trigger:** `⌘K` or `/`.
*   **Style:** Modal centered on screen, `600px` wide.
*   **Features:** Rapid keyboard navigation, recent searches, and quick actions (e.g., "Create Ticket", "Go to Settings").
*   **Highlighting:** Search matches are wrapped in a `#0066FF` text span.

## 19. Analytics
*   **Charts:** Clean, minimal sparklines and bar charts. Remove heavy gridlines. Y-axis uses `1px dashed #E5E7EB`.
*   **Data Series:** Primary data uses `#0066FF`. Comparison data uses `rgba(0, 102, 255, 0.2)`.
*   **Tooltips:** Appear on hover, `#FFFFFF` surface, Elevation 2, detailing exact values.

## 20. Motion
*   **Philosophy:** Fast, purposeful, interruptible.
*   **Micro (Buttons, Toggles):** `150ms ease-out`.
*   **Macro (Drawers, Modals):** `250ms cubic-bezier(0.16, 1, 0.3, 1)`.
*   **Fade:** Opacity transitions use linear easing for smoother visual degradation.

## 21. Responsive Design
*   **Breakpoints:**
    *   `sm`: `640px` (Mobile)
    *   `md`: `768px` (Tablet - Sidebar collapses)
    *   `lg`: `1024px` (Small Desktop)
    *   `xl`: `1280px` (Large Desktop)
*   **Rules:** Fluid typography is not used; rely on fixed sizing per breakpoint. Card grids collapse from 3 columns (`xl`), to 2 (`lg`), to 1 (`sm`).

## 22. Accessibility
*   **Focus Rings:** Non-negotiable `3px` solid `#0066FF` outline offset by `2px` for all interactive elements.
*   **Contrast:** All text guarantees a minimum `4.5:1` contrast ratio against its background.
*   **Semantic HTML:** Use native `<button>`, `<nav>`, `<main>`, and dialog elements. 
*   **Target Size:** Minimum clickable area is exactly `40x40px`.

## 23. Component Library
All components must be constructed as isolated, reusable tokens.
*   **Variants:** Standardize variants (Primary, Secondary, Ghost, Danger) and Sizes (SM, MD, LG).
*   **States:** Every interactive component must define Default, Hover, Focus, Active, and Disabled states.

## 24. Interaction Rules
*   **Destructive Actions:** Require a secondary confirmation (modal or double-click mechanism) and use `#EF4444`.
*   **Loading Feedback:** Any action taking longer than `300ms` must display a loading state.
*   **Hover Intent:** Dropdowns require a `150ms` delay on mouse-leave to prevent frustrating accidental closures.

## 25. Design Tokens
| Token Category | Token Name | Exact Value |
| :--- | :--- | :--- |
| **Color** | `--color-brand-primary` | `#0066FF` |
| **Color** | `--color-bg-canvas` | `#F9FAFB` |
| **Color** | `--color-bg-surface` | `#FFFFFF` |
| **Color** | `--color-text-primary` | `#111827` |
| **Radius** | `--radius-sm` | `4px` |
| **Radius** | `--radius-md` | `8px` |
| **Radius** | `--radius-lg` | `16px` |

## 26. Icons
*   **Style:** Geometrically precise, vector-based, out-lined icons (not solid). 
*   **Stroke Width:** Exactly `1.5px` or `2px`, strictly maintained across all sizes.
*   **Sizing:** `16x16px` (inline text), `20x20px` (buttons), `24x24px` (sidebar).

## 27. Illustrations
*   **Constraint:** Absolutely **no React logos** or similar tech-stack branding in the UI. 
*   **Style:** Minimalist vector art, utilizing the primary `#0066FF` alongside subtle `#E5E7EB` gray shapes. No complex shading or gradients. Keep it flat and geometric.

## 28. Empty States
*   **Layout:** Centered vertically and horizontally.
*   **Visual:** One geometrically precise, minimal vector icon (`48x48px`, `#9CA3AF`).
*   **Copy:** Clear title (`18px`, `#111827`), helpful subtitle (`14px`, `#6B7280`).
*   **Action:** One primary `#0066FF` CTA to initiate the first action (e.g., "Create your first ticket").

## 29. Error States
*   **Inline:** Inputs receive a `1px solid #EF4444` border. Error text (`12px`, `#EF4444`) appears `4px` below the input.
*   **Page Level:** Card-based error boundary displaying a clear, non-technical explanation of the failure and a "Try Again" or "Return Home" CTA.

## 30. Loading States
*   **Initial Page Load:** Use skeletal loading screens. Skeletons should be `#F3F4F6` with a subtle left-to-right shimmer animation.
*   **Inline Action:** A minimal `16px` geometric spinning ring (border-top `#0066FF`, border-right/bottom/left `rgba(0, 102, 255, 0.2)`) replaces the button text or icon during submission.