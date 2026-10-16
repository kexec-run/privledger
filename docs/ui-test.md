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
   - Confirms Python created basic metadata, then submits enrichment from the dialog and checks saved values.
   - Checks recorded media duration/codecs and the cached thumbnail response.

## Commands

Run the default browser suite:

```bash
cd apps/web
npm run test:e2e
```

The npm script invokes `e2e/run-e2e.mjs`, which creates a unique temporary data root before Playwright starts the API and web servers. The fake recorder and all API/Python fixture commands use this root. The test services bind API port `4578` and web port `5174` by default; override with `PRIVLEDGER_E2E_API_PORT` and `PRIVLEDGER_E2E_WEB_PORT`.

Run the hardware-backed recorder test separately:

```bash
cd apps/web
npm run test:e2e:real
```

This uses the local camera configuration and the existing camera helper, but stores generated metadata, media, logs, and SQLite under its own temporary root. A successful run deletes that workspace. A failed or interrupted real-recorder run preserves its workspace and diagnostics under ignored `apps/web/test-results/real-recorder-failures/`.

Pass Playwright selection flags after `--`, for example:

```bash
npm run test:e2e -- --grep calendar
```

Do not invoke Playwright directly for these specs: fixture helpers require `PRIVLEDGER_E2E_ROOT`, supplied by the launcher. The launcher also overrides inherited data-root, database, and pipeline command variables.

## Isolation Checks

The launcher tests verify that it creates only the directories and files needed for an isolated run, does not copy working recordings or cache, replaces inherited path/command overrides with test-local values, and removes only the exact temporary workspace it created. Each browser run starts fresh with an empty `vlog/`, logs directory, and SQLite cache. Integration checks send `SIGINT` after the test servers become ready and `SIGTERM` while a fake recorder is active. They assert that the recorder and both servers stop, the temporary workspace is removed, and an unrelated sentinel file survives. Both signals request Playwright's graceful `SIGINT` teardown; the launcher awaits its completion before deleting test data.

Run these launcher checks with `cd apps/web && npm run test:e2e:launcher`.

The real-recorder test is opt-in because it requires camera and microphone permissions. Its failure artifacts are kept for diagnosis; successful temporary recordings are deleted after the services exit.

## Execution Notes

- Use browser locators for interaction. Do not depend on DOM methods inside browser `evaluate`.
- Check API state through Playwright's request fixture or a shell request, rather than assuming `fetch` exists in browser evaluation.
- The Playwright config starts isolated API/web services and does not reuse any existing listener.
- Fixture-based UI specs pin the browser date to June 29, 2026; recorder specs keep the real clock.
- The fake-recorder spec waits for its readiness marker before sending Stop.
- Disposable metadata fixtures omit `custom` unless the copied custom schema enables it.
- Collect browser console warnings/errors at the end of each flow.
