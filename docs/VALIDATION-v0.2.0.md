# Taleprism v0.2.0 validation

Local integration was verified on macOS with Python 3.12.15, Node.js 26.12.1 and Chrome.

| Check | Observed result |
| --- | --- |
| Backend regression | Full local suite passed with the pinned public Chibi input, optional local historical packs and WebGAL available |
| Frontend and build tools | TypeScript/Vite build, reader model tests, lint, generated prompt/schema checks and public source inventory checks passed |
| Fresh installation | Extracted the curated source into an empty directory, installed locked dependencies with `start.sh`, and opened the workbench with a fresh data directory |
| Public example rebuild | Built both example pairs from the extracted source and the pinned v0.1.0 public Chibi reader. Checked 12 Chibi shots and 3 Last Light shots, source bytes, reader manifests and absence of system demonstration audio |
| Editable project round trip | Imported each sample, changed its reader title, exported the standalone reader, and reimported the edited project. The new project retained the title, source bytes and valid production checks |
| Browser acceptance | Verified draft recovery, review revocation, downstream blocking and re-export in the workbench. Chibi passed desktop and mobile checks under `/taleprism/`, including 12 illustrations, 9 portraits and 3 map phases. A saved v0.1 record restored the illustration, bookmark and reading preferences |

GitHub Actions records the Ubuntu and macOS checks against the release commit. The release manifest and checksum file identify the shipped bytes. Pages deploys the Chibi reader pinned in the example catalog.

Creator final art approval, live OpenAI synthesis and external-user onboarding remain pending.
