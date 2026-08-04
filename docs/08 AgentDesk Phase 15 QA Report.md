# Document 08 — Phase 15 QA Report

Traceability for [Implementation Plan](06%20AgentDesk%20Implementation%20Plan.md) Phase 15:
every Acceptance Criteria item from Document 01 and every named edge case from Document 03
§6, §27 and §28, each mapped to a passing test **or** a documented, deliberate exception.

Exceptions are listed with the reason they cannot be automated here, not hidden. Anything
marked **manual — not executed** is a real gap in this report, not a pass.

Companion document: [`backend/TEST_REPORT.md`](../backend/TEST_REPORT.md) is the Phase 0–8
backend verification pass — endpoint-by-endpoint, with the defect log. It is not superseded
by this one; that report asks "does the backend work?", this one asks "does the product meet
its stated criteria?".

**Two `xfail(strict=True)` tests remain**, both Informational defects carried from that
report: BUG-18 (`GET /tickets?status=nonsense` returns `200 []` rather than rejecting the
filter) and BUG-19 (the in-memory report store is never evicted). Strict marking means either
one turns into a *failure* the moment it is fixed, so neither can rot. Neither touches an
Acceptance Criteria item or a named edge case.

## 0. The one finding that mattered most

**The test suite was sending real email from the developer's own Gmail account, and polling
their real inbox.**

`backend/.env` carries live `SMTP_*` and `IMAP_*` credentials for the demo environment.
`mailer.send_email` only falls back to "write it to the log" when `smtp_host` is *empty*, and
the IMAP poller starts from the app lifespan whenever `IMAP_HOST` and `IMAP_POLL_SECONDS` are
both set — which `TestClient(app)` triggers, because entering it as a context manager runs
the lifespan. `conftest.py` blanked `gemini_api_key` to keep the suite off the real LLM but
never did the same for mail.

Consequences, all observed rather than theorised:

- Every notification the suite generated attempted a real SMTP send to `smtp.gmail.com`,
  measured at **~3.8s per call**.
- The account hit its cap: `550 5.4.5 Daily user sending limit exceeded`.
- One `monitor.scan_once` over a backlog of overdue tickets is hundreds of sends, which
  overran the 60-second hang watchdog and hard-exited the run. That is what turned a green
  suite into 255–315 failures, and it is why the failures looked like unrelated auth errors.

Fixed in `tests/conftest.py`, next to the existing Gemini line: the session `client` fixture
now blanks `smtp_host` and `imap_host` before the app starts. Tests that want to assert on
delivery use the existing `outbox` fixture; this is the floor under every test that does not.

**Operational note for whoever owns the demo account:** the sending quota was consumed and
resets on Google's own schedule. Nothing was sent to real external recipients — the addresses
are all seeded `@agentdesk.dev` / `@example.com` values — but the sends were genuinely
attempted through that account, so they will appear in its outbound activity.

## How to run the suite

```bash
cd backend && .venv/bin/pytest                    # 866 passed, 2 xfailed, ~55s
cd backend && .venv/bin/pytest -m "not slow"      # skips the volume tests
cd frontend && npm run selfcheck                  # shell logic + accessibility
```

That 55 seconds is the *fixed* number. Before §0, the same suite took 12–20 minutes and was
failing 255–315 tests — almost all of it real SMTP round-trips.

The backend suite runs against a live Postgres named `<db>_test`, provisioned automatically.
It has **no per-test rollback** by design — tests isolate by generating unique data. Two
consequences worth knowing before reading a failure:

- The test database accumulates rows across runs. It reached ~21k tickets and 633 *overdue*
  ones during this phase, and that backlog is what made `monitor.scan_once` expensive enough
  to expose the SMTP problem above. `dropdb agentdesk_test` resets it; the next run
  re-creates, migrates and seeds it. Do that before trusting a timing-sensitive result — the
  55-second figure above is from a freshly dropped database.
- **Aggregate assertions are shared state too.** `test_the_ai_trend_report_never_double_counts_a_day`
  asserts `classifications <= drafts` on *today's* bucket across every ticket the caller can
  see. That is not a real invariant — App Flow §14's low-confidence branch ends before the
  draft node, so a classification with no draft is legitimate — and any test that writes
  classification history dated today can tip it. The Acceptance Criteria test that needs such
  rows backdates them by 30 days for exactly this reason.
- A test that relies on being *the* match for a query must make its data unique in the
  dimension the query actually sorts on. See the Phase 14 KB retrieval test, fixed during
  this phase — it was unique by title but not by embedding, so previous runs' articles tied
  with it at cosine distance 0.0 and eventually crowded it out of the `LIMIT 3`.

---

## 1. Acceptance Criteria (Document 01)

Each criterion has a named test in `tests/integration/test_acceptance_criteria.py`, which
exists purely as this traceability layer; depth lives in the per-module suites it points at.

| # | Criterion | Status | Test |
|---|---|---|---|
| 1 | Ticket created with all required fields, confirmation returned | **Pass** | `test_a_created_ticket_returns_a_confirmation_to_the_requester`, `test_a_ticket_missing_a_required_field_is_rejected` |
| 2 | AI classification accuracy >85% agreement with human category | **Exception** — see below | `test_ai_classification_accuracy_is_measured_against_human_corrections` |
| 3 | Auto-routing assigns tickets per configured rules | **Pass** | `test_auto_routing_assigns_a_high_confidence_ticket`, plus `test_ai.py` for the medium/low branches |
| 4 | SLA alerts trigger at the correct threshold | **Pass** | `test_sla_alerts_fire_at_warning_and_at_breach`, plus `test_sla.py` |
| 5 | RBAC enforced (an Agent cannot reach Admin configuration) | **Pass** | `test_an_agent_cannot_reach_admin_configuration`, `test_a_requester_cannot_reach_admin_configuration`, `test_a_requester_cannot_read_another_requesters_ticket`, plus `tests/security/test_permissions.py` |
| 6 | Reports export correctly in CSV/PDF/Excel | **Pass** | `test_a_report_exports_in_each_required_format` (asserts the magic bytes, not just the status code) |

### Exception — AC 2, the 85% accuracy gate

The product **measures** the criterion: `classification_accuracy` in the AI Performance
report is `1 - corrected/total` over `ai_classification_history`, which is literally
agreement with the human-assigned category. The test above pins that this number is computed
honestly (a corrected classification pulls it below 1.0).

What no test in this repo can assert is that the number **exceeds 85%**. That is a property
of a trained DistilBERT checkpoint (gitignored, per CLAUDE.md) evaluated against a labelled
holdout set, and neither is version-controlled here. Verifying the gate means running the AI
Performance report against real graded data.

This stays open alongside the other Phase 5/16 model decisions (final classifier, embedding
dimension, SLA thresholds).

---

## 2. Edge cases — Document 03 §6 (empty / error / loading states)

These are frontend states. Every list screen renders them from React Query's
`isPending` / `isError` through the shared `components/EmptyState.tsx` and
`components/Skeleton.tsx`, so the three states are structural rather than per-screen
hand-rolled.

| Screen | Empty | Error | Loading | Where |
|---|---|---|---|---|
| My Tickets (Requester) | ✅ | ✅ | ✅ | `pages/portal/MyTickets.tsx` |
| Ticket Queue (Agent) | ✅ | ✅ | ✅ | `pages/agent/Queue.tsx` |
| New Ticket form | n/a | ✅ inline + submit banner | ✅ "reviewing your ticket…" | `pages/portal/NewTicket.tsx` |
| Ticket Detail | ✅ | ✅ | ✅ | `pages/portal/TicketDetail.tsx`, `pages/agent/TicketDetail.tsx` |
| Knowledge Base search | ✅ | ✅ | ✅ | `pages/portal/KnowledgeBase.tsx`, `pages/agent/KnowledgeBase.tsx` |
| Reports & Analytics | ✅ "No data" | ✅ failed | ✅ | `components/ReportRunner.tsx` (shared by Admin + Team reports) |
| Notifications | ✅ | ✅ | ✅ | `pages/portal/Notifications.tsx` |
| Automation Rules | ✅ | ✅ inline validation | ✅ | `pages/admin/Automation.tsx`, rule validation in `lib/admin.ts` (selfchecked) |
| Attachment upload | n/a | ✅ size/type, per-file retry | ✅ progress | `components/AttachmentPicker.tsx`, `lib/attachments.ts` (selfchecked) |
| Session Expired | n/a | ✅ 401 → Login | n/a | `routes/RequireAuth.tsx` — preserves `state.from` and replays it after login |

**Verification method:** source audit plus the pure-logic assertions in `npm run selfcheck`.
Rendered-state screenshots are part of the manual pass below, which was not executed.

---

## 3. Edge cases — Document 03 §27 (error recovery flows)

All covered by `tests/edge_cases/test_service_degradation.py` unless noted. The shape of each
test is "kill one dependency, assert the documented fallback still works" — nothing else in
the suite runs with a dependency broken.

| Failure | Documented fallback | Status | Test |
|---|---|---|---|
| AI service unavailable | Ticket still created `New`; routed to manual classification | **Pass** | `test_ai_provider_outage_still_creates_the_ticket`, `test_ai_provider_outage_leaves_the_ticket_for_manual_classification` |
| Notification delivery failure | In-app notification always attempted even if email fails | **Pass** | `test_a_dead_smtp_relay_still_records_the_in_app_notification` |
| Email server unavailable | Portal and chat remain available as intake | **Pass** | `test_an_inbound_email_outage_leaves_the_portal_channel_working` |
| Attachment upload failure | Ticket submittable without it; manual retry | **Pass** | `test_a_failed_attachment_does_not_cost_the_ticket` |
| Search unavailable | List/filter browsing stays usable | **Pass** | `test_ticket_browsing_survives_a_total_search_outage`, `test_search_degrades_to_text_when_the_embedding_provider_is_down` |
| Database timeout | Generic 500, no internals leaked | **Pass** | `test_a_database_timeout_is_a_generic_500_that_leaks_no_internals` |
| Authentication timeout | Session Expired, destination preserved | **Pass** | `test_an_expired_session_is_a_401_not_a_403`; expiry itself in `tests/security/test_auth_security.py`; replay in `routes/RequireAuth.tsx` |
| Rate limit exceeded | Cooldown, automatic recovery | **Pass** | `tests/security/test_rate_limits.py` |

Note on the AI row: the retry-with-exponential-backoff described in §27 is **not**
implemented. `pipeline.run_for_ticket` logs the failure and leaves the ticket for manual
classification — the fallback §27 specifies. Retry is a Phase 16 concern; the tested
behaviour is the terminal state, which is what the user actually experiences.

---

## 4. Edge cases — Document 03 §28 (additional scenarios)

| Scenario | Status | Test / note |
|---|---|---|
| Duplicate ticket detected → flagged, not auto-merged | **Exception** — not built | The pipeline retrieves similar tickets, but only to ground the classifier prompt (`pipeline._retrieve`); no similarity score is surfaced to the assigned agent. The §20 merge flow exists and is tested (`test_merge_closes_secondary_and_links`, `test_a_merge_is_recorded_on_both_tickets`), so a human can merge — but the *detection* half of §28 has no implementation to test. Carry to Phase 16. |
| AI confidence too low → manual classification | **Pass** | `test_low_confidence_stays_unclassified` (`test_ai.py`) |
| Email parsing failure → manual review queue | **Pass** | `test_a_malformed_email_lands_in_the_manual_review_queue` (`test_intake.py`) |
| Attachment virus detected *(future)* | **n/a** | Marked future in Doc 03; no scanner in the prototype. Type + magic-byte validation is tested in `tests/security/test_file_uploads.py`. |
| Automation rule conflict → higher priority wins, logged | **Pass** | `test_conflicting_rules_resolve_by_priority` (`test_automation.py`) |
| No matching agent → queue's unassigned bucket | **Pass** | `tests/integration/test_agent_api.py`, `test_sla.py` |
| Knowledge Base unavailable → suggestions omitted, submission unaffected | **Pass** | `test_a_knowledge_base_outage_does_not_block_ticket_submission` |
| SLA breach during maintenance → still recorded | **Pass** | `test_a_breach_recorded_before_reopen_survives_the_reopen` — timers are server-side and the monitor is driven directly |
| Deactivated user still assigned → flagged for reassignment | **Pass** | `test_a_deactivated_users_tickets_are_reassigned_or_flagged` |
| Reopen after SLA expiry → fresh segment, original breach intact | **Pass** | `test_reopening_starts_a_new_resolution_segment`, `test_sla_set_on_classification_and_fresh_segment_on_reopen`, and `test_a_breach_recorded_before_reopen_survives_the_reopen` for the "unaffected by the reopen" half |

---

## 5. Accessibility pass

Automated by `frontend/scripts/a11y.selfcheck.ts` (`npm run selfcheck`), which parses the
design tokens out of `src/index.css` and **computes** WCAG contrast rather than trusting the
ratios written in the comments beside them. 32 pairs across light and dark.

### Findings and fixes

Three real failures on shipped UI, all now fixed:

1. **White labels on the semantic status colours failed AA, badly.** `bg-success text-white`
   (the *Resolved* status pill, the setup checklist, automation run badges) was **2.54:1**;
   `bg-critical text-white` (the danger button, the notification count badge) was **3.76:1**;
   `bg-high text-white` (*In Progress*, *Reopened*) was **2.15:1**.

   Fixed with the split the palette already used for `primary` and `ai`: the bare token stays
   the Doc 07 hue and remains correct as text, borders, icons and SLA scrubber bars — none of
   which put white on top of it — and a new `-fill` variant carries white labels.
   `--color-critical-fill` `#DC2626` (4.8:1), `--color-high-fill` `#B45309` (5.0:1),
   `--color-success-fill` `#047857` (5.5:1). `medium` needed none; `#6B7280` already carries
   white at 4.8:1.

2. **`--color-muted` failed on the sunken surface.** `#6B7280` on `#F3F4F6` is **4.39:1** —
   AA everywhere except the two places muted text actually lands on sunken: input
   placeholders and hovered table rows. Darkened to `#697079` (4.55:1 on sunken, 4.79:1 on
   canvas). Barely perceptible; fixes the hover state.

3. **Priority pills hardcoded white on an admin-chosen hex.** `priorities.color_hex` is
   editable, so no token can guarantee its contrast, and the seeded values were the worst
   case — white on the seeded Low green `#34D399` is **1.9:1**. `PriorityPill` now computes
   its foreground with `readableOn()` (`lib/ui.ts`), which picks ink or white by WCAG
   luminance. All six seeded/palette colours now clear 4.5:1, asserted in the selfcheck.

Also added: a global `:focus-visible` rule in `index.css` as a floor under the existing
`focusRing` utility (used in 42 files), so an element that forgets the utility still gets the
Doc 07 §22 ring instead of silently becoming keyboard-invisible. Same values, so the two
cannot disagree.

### Verified already correct

- **Reduced motion** — `@media (prefers-reduced-motion: reduce)` kills every animation and
  transition globally; asserted by the selfcheck.
- **Focus ring** — 3px `--color-primary`, 2px offset, and never removed: the selfcheck fails
  on any `outline: none` in the stylesheet.
- **Colour is never the only signal** — status and priority pills always carry a text label;
  the AI violet is always paired with a label (a codebase invariant, see CLAUDE.md).
- **Target size** — `tapTarget` is 44px, above Doc 07 §22's 40px web minimum.

### Documented exception

`--color-primary` on `--color-sunken` is **4.39:1**. Doc 07 §25 pins `#0066FF` exactly, so
the token cannot be darkened, and interactive text is never rendered on a sunken fill today
(inputs switch to `bg-surface` on focus; hovered rows carry ink and muted, not primary). The
selfcheck records it as an allowed exception and **fails if it ever stops firing**, so a
stale entry cannot rot in place.

### Manual — not executed

Keyboard-only navigation through ticket submission, ticket resolution and admin
configuration, and screen-reader announcement checks on status pills, SLA scrubber positions
and AI reasoning panels, both need a real browser and an assistive-technology bridge. Neither
was run for this report. The static preconditions are in place (semantic elements, the focus
ring, `aria-label`s on the AI chips) but that is not the same as a walkthrough, and this
report does not claim it is.

---

## 6. Load and query-plan pass

Covered by `tests/performance/test_bulk_operations.py` (marked `slow`). Thresholds are
deliberately loose — the point is to catch a *change in shape*, not to police milliseconds on
developer hardware.

| Check | Test |
|---|---|
| Bulk creation stays linear | `test_bulk_ticket_creation_stays_linear_and_consistent` |
| List endpoint holds up at 1000+ tickets | `test_a_thousand_tickets_do_not_degrade_the_list_endpoint` |
| Deep pagination does not degrade | `test_deep_pagination_does_not_slow_down` |
| No N+1 on list / users / search / dashboard | `test_listing_tickets_issues_a_constant_number_of_queries`, `test_listing_users_is_not_n_plus_one_on_roles`, `test_search_issues_a_bounded_number_of_queries`, `test_the_dashboard_issues_a_bounded_number_of_queries` |
| Search latency on a populated table | `test_search_latency_is_acceptable_on_a_populated_table` |
| **`EXPLAIN` confirms the index is used** | `test_the_search_index_is_actually_used` — asserts `ix_tickets_fts` appears in the plan, with `enable_seqscan = off` so the test asks "can this query use the index" rather than second-guessing the planner |
| Doc 05 indexes exist | `test_checkpoint_indexes_present` (`test_schema.py`) |
| Report generation and export at full-table scale | `test_report_generation_scales_to_the_whole_table`, `test_a_large_report_export_completes` |

**Gap:** only the FTS index is confirmed *in use* by `EXPLAIN`; the rest are confirmed to
exist. Extending plan assertions to the trigram and HNSW indexes is worthwhile but was not
done here.

---

## 7. Security pass

| Requirement | Status | Test |
|---|---|---|
| Rate limiting works | **Pass** | `tests/security/test_rate_limits.py` |
| All queries parameterised, no string-built SQL | **Pass** | `test_no_sql_is_built_by_string_formatting` — an AST scan of every `text()` call in `app/`, requiring a literal argument; `test_raw_sql_that_takes_a_value_binds_it` for the corollary. Behavioural coverage in `tests/security/test_sql_injection.py`. |
| No sensitive field in any response body | **Pass** | `test_no_response_body_carries_a_sensitive_value` (20 endpoints × 4 roles), `test_a_single_user_and_ticket_detail_carry_no_hashes` |
| No sensitive field in any log | **Pass** | `test_no_log_line_carries_a_sensitive_value` |
| Admin/Team-Lead screens unreachable by direct URL | **Pass** | `test_an_agent_cannot_reach_admin_configuration`, `test_a_requester_cannot_reach_admin_configuration`, `tests/security/test_permissions.py` |
| Errors leak no internals | **Pass** | `test_an_unhandled_error_does_not_return_a_stack_trace` |

The secret checks match on the **actual values** pulled from the database, not on field
names — a serialiser that renamed the field would still fail. `webhooks.secret` is checked in
both representations (the plaintext returned once at creation, and the ciphertext stored in
the column), and the fixture creates a webhook because the table is empty at rest, which
would otherwise have made that third of the checkpoint vacuous. The fixture also asserts each
needle is ≥16 characters, so a short or blank value cannot turn the scan into noise.

---

## 8. Checkpoint status

- [x] **Every Acceptance Criteria item and every named edge case has a passing test or a
      documented, deliberate exception.** Two exceptions, both above: the AC 2 accuracy
      threshold (needs a graded dataset) and §28 duplicate detection (not built).
- [x] **No `password_hash`, `token_hash` or `webhooks.secret` value appears in a response or
      log.** Asserted continuously by `tests/security/test_secret_exposure.py` rather than by
      a one-off grep of a run's output, so it holds for future runs too.
- [ ] **Keyboard-only navigation completes ticket submission, ticket resolution and admin
      configuration with no mouse.** **Not executed** — needs a browser. The focus ring is now
      in place globally, which was the missing precondition, but the walkthrough itself is
      outstanding.

## 9. Outstanding manual passes

Neither was executed for this report; both need a real browser.

1. **Cross-browser** — latest Chrome, Firefox, Edge, Safari.
2. **Responsive** — the Doc 07 §21 breakpoints (card grids collapsing 3 → 2 → 1), plus
   tablet and mobile layouts.

The build is a standard Vite/React target with no browser-specific APIs and no vendor
prefixing beyond what Tailwind emits, so the risk is low — but low risk is not a pass, and
these lines stay unchecked until someone runs them.

## 10. Changes made during this phase

- **Fixed** the live SMTP/IMAP leak in `tests/conftest.py` (§0) — the most consequential
  change in this phase.
- **Fixed** a self-poisoning flake in `test_a_published_article_is_retrieved_for_a_similar_ticket`
  (see "How to run the suite" above).
- **Fixed** a shared-state bug of my own making: the `secret_values` fixture originally
  created an *active* `ticket_created` webhook and never deleted it. Twelve of them
  accumulated, firing 6,132 delivery attempts against every ticket the suite created. It now
  creates the webhook inactive and deletes it on teardown. Worth recording because it is the
  same root cause as the two items above — a shared database with no rollback punishes any
  test that leaves a row behind.
- **Added** `tests/integration/test_acceptance_criteria.py`, `tests/edge_cases/test_service_degradation.py`,
  `tests/security/test_secret_exposure.py` — 39 tests.
- **Added** `frontend/scripts/a11y.selfcheck.ts`, wired into `npm run selfcheck`.
- **Fixed** the contrast failures in §5, in `frontend/src/index.css`,
  `components/StatusPill.tsx`, `components/Button.tsx`, `shell/TopBar.tsx`,
  `pages/admin/Setup.tsx`, `pages/admin/Automation.tsx`, `pages/agent/KnowledgeBase.tsx`.
- **Added** `readableOn()` to `frontend/src/lib/ui.ts`.
- **Added** the global `:focus-visible` floor to `frontend/src/index.css`.
