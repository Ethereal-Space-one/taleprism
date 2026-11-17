# Taleprism v0.3.3 validation

Local release-candidate checks based on `dead785875cea79d261d085c390b67d793143ab8`. All listed checks ran on Linux, Python 3.12.14 and Node 24.22.1, not the Ubuntu/macOS GitHub matrix.

## Executed locally

- Exact public v0.1.0 Chibi reader downloaded and verified at SHA-256 `b8597e51982dfc23acd10cdb99caf0e75cb616a599e4049ce9fb217a87adf84a`.
- Frontend TypeScript/Vite production build passed; all nine reader model-check stages passed, including bounded environment-motion/evidence/lifecycle checks.
- Ruff, generated prompt/schema check and 298-file explicit source inventory passed.
- Focused backend aggregate: 152 passed, 5 skipped for optional local historical/engine/full-sample inputs. Review aggregate excluding export: 7 passed, 2 deselected.
- After freezing both example pairs and updating the catalog/fixed guided pins: guided-sample/release/version aggregate 29 passed, including the complete Last Light sample and exact frozen-cache tests. Mocked transport boundary tests remain unchanged.
- Both public examples rebuilt with all network socket connections blocked. Source preservation, clean import/re-export, assistant checks, silent samples, Chibi 27 original image bytes, stable public work ID and 12 legacy plate IDs passed.
- Both standalone readers independently verified with `prepare_pages --archive`, including exact outer SHA-256, every internal byte count/hash and exact inventory, then extracted to local verification directories only. No Pages action was run.
- A curated source archive installed into a separate fresh environment with `uv sync --frozen` (29 packages) and `npm ci` (73 packages); the extracted source frontend built successfully. With network sockets blocked, a fresh data workspace imported both frozen projects without restore issues and re-exported both standalone readers; source hashes were preserved.
- These results are software checks, not creator art approval or an external-user onboarding trial.

## Remaining release gates

Actual Ubuntu/macOS workflows for the final release commit; macOS Finder/Gatekeeper launcher acceptance; Safari and physical-phone/touch acceptance; creator final art review and external-user onboarding; actual attachment re-download/verification; and actual Pages deployment/rollback evidence are not established by the local checks recorded here. Chibi fire-ship flag-color paired-shot continuity remains `needs_revision` with no art correction applied.

Frozen example ZIPs contain run-specific project/export IDs and timestamps. Their exact hashes identify the frozen build, not reproducible future ZIP bytes. Versioned download links become available only when the corresponding release attachments have been published.
