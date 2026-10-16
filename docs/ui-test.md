# Privledger UI Playwright Test Plan

This document lists the current web UI surfaces and the browser checks to run with Playwright.

## Test Surfaces

| UI surface | Expected behavior | Playwright check |
| --- | --- | --- |
| Topbar / brand / status | Shows app name, recorder state, and global actions. | Load the app and assert `Privledger`, recorder status, `Record`, `Screenshot mode`, and `Refresh Index` render. Assert no dead `Open menu` button exists. |
| Record button | Opens prepare mode without starting the recorder. | Click `Record`; assert `Prepare recording`, `Start recording`, `Cancel`, no timer, no `Stop recording`; check `/api/status` remains `idle`. |
| Screenshot mode | Toggles privacy mode. | Click `Screenshot mode`; assert control text/state changes and privacy blur classes are applied to sensitive media/transcript surfaces when present. |
| Refresh Index | Refreshes the SQLite-derived index and reloads UI data. | Click `Refresh Index`; assert no console errors and the calendar/list still render. |
| Calendar month controls | Moves between months. | Click previous/next month; assert the month heading changes and the day grid updates. |
| Calendar day grid | Selects a local date and loads recordings. | Select a known recording day such as `2026-06-29`; assert day header and recording count update. |
| Tag list | Filters recordings by tag. | Click a tag; assert tag row is active and the day header shows matching count. Click `All recordings` and assert reset. |
| Index card | Shows derived SQLite cache size and source-of-truth copy. | Assert `Index size`, record count, and `SQLite cache · source of truth remains vlog/` render. |
| Day header sort toggle | Toggles recording order. | On a day with multiple recordings, record first card time, click `Start time ↓/↑`, assert label and first card order change. |
| Recording list cards | Selects recordings. | Click a recording card; assert it becomes selected and the inspector title matches. |
| Empty recording state | Explains empty days/filters. | Select an empty day; assert `No recordings for this filter`. |
| Inspector panel | Shows selected recording details. | Assert media, life metadata, enrichment, transcript summary, and metadata sections render for a selected recording. |
| Inspector close | Hides and reopens details. | Click `Close inspector`; assert `Select a recording` and no selected card. Click a card; assert inspector reopens and card is selected. |
| Media block | Shows thumbnail/fallback and duration, without playback controls. | Assert media status, duration, and thumbnail/fallback render. Assert no play button is exposed. |
| Life metadata chips | Shows existing schema fields. | Assert mood, energy, stress, sleepiness, sleep hours, and optional caffeine/body weight chips render with values or dashes. |
| Enrich metadata | Opens metadata form. | Click `Enrich metadata`; assert form fields and tag vocabulary render from API data. |
| Enrichment validation | Rejects invalid values and allows valid values. | Fill invalid numeric values and submit; assert field errors and preserved input. Correct with an in-range value, such as `4`, and assert errors clear. Do not treat blanking an optional field as the correction check unless the UI explicitly supports that path. |
| Metadata controls | Toggles raw metadata JSON. | Click `Metadata`; assert JSON appears. Click again to collapse. Click `Open JSON`; assert JSON is visible. |
| Transcript summary | Shows transcript or no-transcript state. | For no transcript, assert disabled `Show more`. For transcript fixture, assert preview and `Show more` toggles extra text. |
| Recording guide accordion | Expands/collapses questions. | In prepare mode, click guide sections; assert one/none expanded, smooth state change, and original order preserved. |
| Start recording | Starts recorder only from prepare mode. | With fake recorder, click `Start recording`; assert API state becomes `recording`, timer appears, and `Stop recording` appears. |
| Stop recording | Stops recorder and opens enrichment. | With fake recorder, click `Stop recording`; assert saving state, refreshed index, selected latest recording, and enrichment dialog. |
| Session enrichment dialog | Adds metadata after recording. | After fake stop, assert enrichment form renders; test `Enrich later` closes dialog and manual enrichment can reopen from inspector. |
| Console/runtime health | No browser runtime errors. | For every flow, collect console warnings/errors and fail on relevant app errors. |

## Implemented Test Files

1. `apps/web/e2e/app-smoke.spec.ts`
   - App shell loads.
   - No dead `Open menu` button exists.
   - Screenshot mode applies privacy blur to a deterministic media fixture.

2. `apps/web/e2e/calendar-and-filter.spec.ts`
   - Previous/next month controls work.
   - Selecting June 29 shows deterministic fixture recordings.
   - Tag filtering and reset work.
   - Empty date state works.

3. `apps/web/e2e/recording-list-inspector.spec.ts`
   - Sort toggle changes order.
   - Card selection opens inspector.
   - Close inspector works.
   - Metadata toggle works.
   - Media block has no playback button.

4. `apps/web/e2e/recording-prepare.spec.ts`
   - `Record` opens prepare mode.
   - Prepare mode does not start the API recorder.
   - `Cancel` closes with recorder still idle.
   - Guide accordion expands/collapses without reordering.

5. `apps/web/e2e/recording-fake-recorder.spec.ts`
   - Uses fake recorder only.
   - `Start recording` calls API.
   - `Stop recording` opens session enrichment.
   - Real camera is not touched.
   - Test-created fake `vlog/e2e-fake-*.json` and `.mov` artifacts are deleted after the run and `/api/index/refresh` is called.

6. `apps/web/e2e/enrichment.spec.ts`
   - Opens enrichment form against a disposable fixture.
   - Invalid numeric values show field errors and preserve input.
   - Valid correction submits through API and closes the form.
   - Fixture metadata/media are deleted after the run and `/api/index/refresh` is called.

7. `apps/web/e2e/recording-real.spec.ts`
   - Uses the real Python recorder pipeline.
   - Starts recording from prepare mode.
   - Stops recording from the dialog.
   - Verifies a new latest recording appears.

## Commands

- `cd apps/web && npm run test:e2e`
  - Starts isolated API/web servers on API `4578` and web `5174`.
  - Uses fake recorder for recording tests.
  - Excludes `@real-recorder`.

- `cd apps/web && npm run test:e2e:real`
  - Starts isolated API/web servers on API `4578` and web `5174`.
  - Uses the real Python recorder pipeline.
  - Runs only `recording-real.spec.ts`.
## Current Verification Result

Latest verification on 2026-10-16 used a temporary source snapshot with its own
`config/env`, `vlog/`, `logs/`, and SQLite cache. The browser checks started their
API and web servers automatically.

1. `cd apps/api && npm test && npm run build`
   - Result: `18 passed`; API build passed.
2. `python3 -m pytest -q`
   - Result: `103 passed`.
3. `cd apps/web && npm run build`
   - Result: passed.
4. `cd apps/web && npm run test:e2e`
   - Result: `9 passed`, including enrichment rejection and correction.
5. `cd apps/web && npm run test:e2e:real`
   - Result: `1 passed`, including the extracted life metadata component after recording.
6. `scripts/dev.sh` start/status/restart/stop with separate ports and synthetic data
   - Result: both services became healthy; stop left no listening processes.

The real-recorder test creates a real recording in the checkout running the tests.
This verification kept it in the temporary source snapshot. Fake-recorder and
fixture specs clean up their generated files.

## Execution Notes

- Prefer browser locators for clicks. In the in-app browser runtime, DOM methods inside `evaluate`, such as `element.click()`, may not be available.
- Do not assume `fetch` is available inside browser `evaluate`; check API state with `curl` or test helpers outside the page when needed.
- The committed Playwright config starts isolated API/web servers on API `4578` and web `5174`.
- The default E2E suite uses `apps/web/e2e/fixtures/fake-recorder.mjs`; the real camera is touched only by `npm run test:e2e:real`.
- Fake-recorder tests assert cleanup: generated fake `vlog/TS.json`, fake media, and derived SQLite rows must be gone after refresh.
- Disposable UI fixtures should omit `custom` unless a custom schema is enabled; `enrich.py` rejects any `custom` key when no custom schema is active.
- Fixture-based specs use `setFixtureDate` to fix the browser date to June 29, 2026; recorder specs keep the real clock.
- The fake-recorder spec waits for the fixture's readiness message before sending Stop, so startup timing cannot suppress its signal handler.
- The default test configuration uses its checkout's data directory. Run it in a disposable source snapshot when the working checkout contains recordings; assumptions about empty dates otherwise depend on those files.
- Always collect browser console warnings/errors at the end of each flow.

## Better Automation Shape

1. Add CI grouping: smoke/calendar/inspector on every UI change; fake recorder and enrichment before merge; real recorder only on local/manual hardware runs.
2. Move disposable E2E fixture writing behind a shared helper that can later target a temporary repo root instead of the working `vlog/`.
3. Add one transcript fixture day so transcript summary expansion is tested, not only the no-transcript state.
4. Add a screenshot-mode visual check with a small screenshot diff or DOM style assertion to prove thumbnail/transcript surfaces are blurred.
5. Add an API-level test for the no-custom-schema payload invariant: UI should omit `custom` when custom enrichment is disabled.
