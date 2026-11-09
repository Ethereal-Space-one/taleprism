# Taleprism 0.1.0 compatibility

Taleprism is the public name of the earlier 原页 / Storygal local project. This release updates visible branding without moving existing projects or renaming persisted identifiers.

| Identifier | Kept for compatibility |
| --- | --- |
| Python package and server | `storygal`, `storygal.app:app` |
| Configuration | `STORYGAL_DATA_DIR`, `STORYGAL_PORT`, `STORYGAL_LLM_*` and existing key aliases |
| Editable-project payload | `storygal-project` v2; v1 imports remain supported |
| Image task format | `storygal-image-tasks` v2; adds template metadata and ordered reference responsibilities |
| Browser state | Existing `storygal-project` and `storygal-reader:*` keys |
| Reader export | Existing meta marker, source directory and inventory names |
| Old macOS launchers | “打开原页.command” and “停止原页.command” continue working |

New download filenames use Taleprism; filenames do not change the internal protocol. Product version 0.1.0, template version 0.1.0 and project format version 2 are separate.

The UI remains Chinese. Native Windows startup is not implemented. Local synthesis is macOS-specific; playing already accepted audio is portable. Public examples omit system-generated demonstration audio. A downloaded project contains its author's production checks, not the recipient's final approval.

Large historical Chibi assets and packed ZIPs are not in the lightweight checkout. Existing local copies remain untouched. Missing optional sample packs now give a download/import instruction instead of an unhandled file error. The canonical Last Light reference images remain in source so the tutorial and release builder do not depend on an unpublished release.
