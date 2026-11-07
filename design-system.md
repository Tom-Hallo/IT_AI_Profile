# IT Talent AI Profile v2.0 — Design System (PBI-004)

## 1. Scope

Original iOS/macOS-inspired UI implementation interpreted from the nine supplied Figma screenshots. No Apple icons, fonts, illustrations, or other proprietary assets are copied. This is a **reusable design-system and one dashboard reference**, not an implementation of every product screen. All scores, GitHub data, audit claims and AI text in the demo are fixtures.

## 2. Setup

From `frontend/`, run `python -m http.server 5500`, then visit `http://localhost:5500`. Use a local HTTP server because JavaScript uses ES modules. No build step, npm, CDN, or external assets required.

## 3. Stylesheet order

```html
<link rel="stylesheet" href="/css/tokens.css">
<link rel="stylesheet" href="/css/base.css">
<link rel="stylesheet" href="/css/components.css">
<link rel="stylesheet" href="/css/layout.css">
```

Paths above assume frontend is served from `/`. If using the included `index.html`, relative paths are already correct.

## 4. Tokens

- **Semantic colors:** `--color-primary`, `--color-secondary`, `--color-bg`, `--color-surface`, `--color-surface-muted`, `--color-glass`, `--color-text`, `--color-text-muted`, `--color-border`, `--color-ring`, `--color-success`, `--color-danger`.
- **Typography:** `--font-sans`, `--font-mono`, `--text-xs` through `--text-2xl`, `--weight-*`, `--leading-*`.
- **Spacing:** `--space-1` (4px), `--space-2` (8px), `--space-3` (12px), `--space-4` (16px), `--space-6` (24px), `--space-8` (32px); `--space-5` (20px) for intermediate rhythm.
- **Radius:** `--radius-sm`, `--radius-md`, `--radius-lg`, `--radius-xl`, `--radius-pill`.
- **Effects:** `--shadow-card`, `--shadow-float`, `--blur-glass`.

Always use semantic tokens in new UI instead of copying hard-coded hex colors. Token values were estimated from screenshots, **not exported from Figma Dev Mode**; verify exact design values before visual sign-off.

## 5. Reusable component examples

```html
<button class="btn">Standard</button>
<button class="btn btn--primary">Primary</button>
<button class="btn btn--ghost">Ghost</button>
<button class="btn btn--danger">Danger</button>
<button class="btn btn--primary" disabled>Disabled</button>
<article class="card card--glass">Glass card</article>
<span class="badge badge--success">Verified</span>
<div class="field">
  <label for="example-email">Email</label>
  <input id="example-email" class="input" type="email" aria-describedby="example-error">
  <span id="example-error" class="field-error" aria-live="polite"></span>
</div>
```

The modal is a native `<dialog>` opened with `.showModal()` and closed with `.close()`, supporting Escape and built-in focus handling. The AI side drawer includes an explicit Tab trap and focus restoration. Native HTML validation is supplemented with `aria-invalid` and a visible error.

## 6. Responsive and accessibility

- Desktop: 236px sidebar; 4-column metrics; 2-column analysis; 3-column repository cards.
- Tablet (`<=1100px`): 2-column metrics, 1-column analysis, 2-column repositories.
- Mobile (`<768px`): collapsible sidebar, 1-column analysis/repositories, responsive topbar.
- `:focus-visible` applies to links, buttons, inputs, textarea, select and focusable chart vertices.
- `prefers-reduced-motion: reduce` disables nonessential transitions and animations.
- Maintain text contrast when customizing the translucent glass surface. The screenshots are light mode; dark mode is an original derived palette, not a Figma export.

## 7. API and authorization boundaries

The demo performs **no API requests** and does not alter FastAPI routes. To integrate into the existing frontend, migrate shared CSS incrementally, then connect page data using the project's existing API client. Preserve existing URL paths, authentication, CSRF protections, JWT/cookie handling, request/response contracts, and error states.

Never infer authorization from a hidden UI element. The backend must validate roles and resource ownership on every protected endpoint. In production, do not present fixture claims such as “verified”, “ZDR compliant”, “SOC-2”, or “SHA-256 signed” unless backed by real evidence and documented guarantees.

## 8. Acceptance testing checklist

- [ ] Load page on Chrome, Edge, Firefox, and Safari.
- [ ] Check 320px, 375px, 768px, 1024px, 1440px widths; verify no horizontal overflow.
- [ ] Tab through navigation, radar vertices, buttons, form fields and modal; focus visible.
- [ ] Open modal; Escape closes and focus returns to trigger.
- [ ] Open agent drawer; Tab stays within drawer; Escape closes and focus returns.
- [ ] Set OS reduced motion; transitions are disabled.
- [ ] Toggle light/dark; reload and verify saved preference.
- [ ] Enter invalid email; check error styling and aria-invalid.
- [ ] Filter repositories; check empty state.
- [ ] Integrate API and verify 200/400/401/403/500, loading, empty and retry flows.
- [ ] Verify authorization with backend tests for Developer/Recruiter/Admin roles.
- [ ] Compare tokens and spacing against Figma Dev Mode.

## 9. Out of scope

Full implementation of the other eight screens, live radar/AST/GitHub data, live AI chat, audit exports, compliance certification, role-based authorization and FastAPI integration are separate PBIs. PBI-004 cannot be marked fully accepted against the live repo until integration and cross-browser/manual accessibility tests are completed.
