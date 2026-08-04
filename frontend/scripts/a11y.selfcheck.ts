/**
 * Accessibility self-check (Implementation Plan Phase 15). Run it with:
 *
 *   npm run selfcheck:a11y
 *
 * Doc 07 §22 and DESIGN.md fix four things that a human pass can confirm once
 * and then silently lose on the next token edit: contrast ratios, the focus
 * ring, reduced motion, and target size. Those are the ones checked here, by
 * reading `src/index.css` and computing the ratios rather than trusting the
 * comments next to the tokens — a comment saying "4.7:1" is not a test.
 *
 * Deliberately not here: keyboard-order and screen-reader-announcement checks.
 * Both need a real browser and an AT bridge; they are the manual half of the
 * Phase 15 pass and are recorded in docs/08 (Phase 15 QA Report).
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const cssPath = fileURLToPath(new URL('../src/index.css', import.meta.url))
const css = readFileSync(cssPath, 'utf8')

// --- WCAG 2.1 relative luminance + contrast ---------------------------------

function srgbToLinear(channel: number): number {
  const c = channel / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  const value = hex.replace('#', '')
  const full =
    value.length === 3
      ? value
          .split('')
          .map((c) => c + c)
          .join('')
      : value
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16))
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

// Sanity-check the maths against the two ratios WCAG itself pins.
assert.equal(Math.round(contrast('#ffffff', '#000000')), 21)
assert.equal(Math.round(contrast('#ffffff', '#ffffff')), 1)

// --- Token extraction --------------------------------------------------------

/** Hex tokens declared inside a given block (`:root` here is the `@theme` one). */
function tokensIn(blockStart: string): Record<string, string> {
  const start = css.indexOf(blockStart)
  assert.ok(start !== -1, `${blockStart} block not found in index.css`)
  // Blocks are flat (no nested braces) in this file, so the first `}` ends it.
  const block = css.slice(start, css.indexOf('\n}', start))
  const out: Record<string, string> = {}
  for (const [, name, hex] of block.matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})/g)) {
    out[name] = hex
  }
  return out
}

const light = tokensIn('@theme {')
const darkOverrides = tokensIn('.dark {')
const dark = { ...light, ...darkOverrides }

assert.ok(Object.keys(light).length > 10, 'expected the light palette to be parsed')
assert.ok(Object.keys(darkOverrides).length > 5, 'expected the dark overrides to be parsed')

// --- Contrast: body text on every surface it can land on ---------------------

const SURFACES = ['canvas', 'surface', 'elevated', 'sunken'] as const
const failures: string[] = []
const allowed: string[] = []

/**
 * Deliberate exceptions, per the Phase 15 checkpoint. Each needs a reason that
 * says why the pairing cannot simply be fixed — an entry here is a decision, not
 * a snooze button.
 */
const EXCEPTIONS: Record<string, string> = {
  'light: primary on sunken':
    '4.39:1. Doc 07 §25 pins --color-brand-primary to exactly #0066FF, so the ' +
    'token cannot be darkened. Interactive text is never rendered on a sunken ' +
    'fill: inputs switch to bg-surface on focus, and hovered rows carry ink and ' +
    'muted, not primary. Revisit if a link is ever placed inside a sunken block.',
}

function check(scheme: string, fg: string, bg: string, min: number, label: string) {
  const ratio = contrast(fg, bg)
  if (ratio < min) {
    const key = `${scheme}: ${label}`
    if (key in EXCEPTIONS) {
      allowed.push(`${key} — ${ratio.toFixed(2)}:1`)
      return
    }
    failures.push(`${key} — ${ratio.toFixed(2)}:1, needs ${min}:1`)
  }
}

for (const [scheme, palette] of [
  ['light', light],
  ['dark', dark],
] as const) {
  for (const surface of SURFACES) {
    const bg = palette[surface]
    // Doc 07 §22: 4.5:1 on all text. `ink` is body copy, `muted` is secondary
    // copy — both are body-size, so neither gets the 3:1 large-text allowance.
    check(scheme, palette.ink, bg, 4.5, `ink on ${surface}`)
    check(scheme, palette.muted, bg, 4.5, `muted on ${surface}`)
    // Interactive text (links, active nav) and the AI accent are body-size too.
    check(scheme, palette.primary, bg, 4.5, `primary on ${surface}`)
    check(scheme, palette.ai, bg, 4.5, `ai on ${surface}`)
  }

  // Solid fills carrying a white label — status pills, the primary CTA, the
  // danger button. Every token a `text-white` class sits on belongs in this list.
  for (const fill of [
    'primary-fill',
    'ai-fill',
    'critical-fill',
    'high-fill',
    'success-fill',
    'medium',
  ] as const) {
    assert.ok(palette[fill], `${scheme}: --color-${fill} is missing`)
    check(scheme, '#ffffff', palette[fill], 4.5, `white on ${fill}`)
  }
}

assert.equal(failures.length, 0, `contrast failures:\n  ${failures.join('\n  ')}`)

// An exception that no longer fires is stale — it should be deleted, not kept.
for (const key of Object.keys(EXCEPTIONS)) {
  assert.ok(
    allowed.some((entry) => entry.startsWith(key)),
    `stale exception in EXCEPTIONS: "${key}" now passes and should be removed`,
  )
}

// --- The rules Doc 07 calls non-negotiable -----------------------------------

// A focus ring that only recolours a 1px border is not a keyboard affordance.
assert.match(
  css,
  /:focus-visible\s*\{[^}]*outline:\s*3px solid var\(--color-primary\)/,
  'Doc 07 §22: every interactive element needs the 3px --color-primary focus ring',
)
assert.match(
  css,
  /:focus-visible\s*\{[^}]*outline-offset:\s*2px/,
  'Doc 07 §22: the focus ring is offset by 2px',
)
// `outline: none` anywhere would undo it globally — DESIGN.md says "never removed".
assert.doesNotMatch(
  css,
  /outline:\s*(none|0)\b/,
  'the focus ring must never be removed (DESIGN.md, Accessibility)',
)

assert.match(
  css,
  /@media \(prefers-reduced-motion: reduce\)/,
  'Doc 04/07: reduced motion is respected globally',
)

// --- Admin-chosen colours ----------------------------------------------------
// `priorities.color_hex` is editable, so no token can guarantee its contrast.
// The pill picks its own foreground instead; pin that it actually flips.
const { readableOn } = await import('../src/lib/ui.ts')
assert.equal(readableOn('#34D399'), '#111827', 'the seeded Low green needs ink, not white')
assert.equal(readableOn('#F05252'), '#111827', 'the seeded Critical red needs ink')
assert.equal(readableOn('#0B0E14'), '#ffffff', 'a near-black fill needs white')
assert.equal(readableOn('#ffffff'), '#111827')
assert.equal(readableOn('nonsense'), '#ffffff', 'a malformed hex must not throw')
for (const hex of ['#34D399', '#8A93A6', '#F5A623', '#F05252', '#0066FF', '#7C3AED']) {
  const ratio = contrast(readableOn(hex), hex)
  assert.ok(ratio >= 4.5, `priority pill ${hex} reaches only ${ratio.toFixed(2)}:1`)
}

console.log(
  `a11y.selfcheck: all assertions passed ` +
    `(${SURFACES.length * 4 * 2} contrast pairs across light + dark` +
    `, ${allowed.length} documented exception${allowed.length === 1 ? '' : 's'})`,
)
for (const entry of allowed) console.log(`  exception: ${entry}`)
