# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A ComfyUI custom-node package (standard library only, no pip dependencies) with two nodes: **Load Script File** and **Shot Script Parser**. They turn a `### SHOT n` script into the `start-end: prompt` text the NG Director node expects. See `README.md` for the script format and user-facing behavior.

## Commands

```
python3 -I -m unittest discover -s tests -v                          # all tests
python3 -I -m unittest tests.test_shot_script.ParserTests.<test_name>  # single test
```

There is no build or lint step. To try it in ComfyUI, copy or symlink the folder to `ComfyUI/custom_nodes/ComfyUI-Shots-Parser` and restart ComfyUI.

## Architecture

- `shot_parser.py` holds all parsing logic and has **no ComfyUI imports**. That is deliberate, so it can be unit tested alone. `parse_script()` returns a `ParseResult` with `errors`, `warnings`, `shots_text`, and a human-readable `report`.
- `js/load_script_file.js` (served via `WEB_DIRECTORY = "./js"`) adds the **Choose file...** button to Load Script File. It posts the picked file to `/shot_script/upload` (`upload_route.py`, which imports ComfyUI's `server` and is therefore imported inside try/except in `__init__.py`), and `nodes.save_upload` stores it in the input folder. Browsers never expose a local path, so uploading into `input` is the only way to "select a file". The JS and the route are not covered by tests; only `save_upload` is.
- `nodes.py` is a thin ComfyUI wrapper and imports `folder_paths`, which only exists inside ComfyUI. `__init__.py` registers the node mappings.
- `nodes.py` imports the parser with a relative import (`from .shot_parser import ...`), so it only works when loaded as a package. The tests import `shot_parser` directly (`sys.path` insert), and they exercise `nodes.py` through a stubbed `folder_paths` module. The nodes have not been run in a real ComfyUI.

## Behaviors to preserve

- **Film length is derived from the parsed shots**: `total_seconds = shot_seconds * len(shots)`. Never count markers separately from the parsed shots. That mismatch was the "phantom shot" bug this package exists to fix.
- **Time is packed back to back.** Gaps in shot ids do not create empty time. All shots share one length (`shot_seconds`), because the Director plans equal parts. Per-shot header ranges are only used for a warning.
- **Strictness is in the node, not the parser.** The parser collects `errors` and never raises. `ShotScriptParser.parse` raises `ValueError` when `strict` is on, so a bad script fails before any rendering.
- `normalize_newlines` strips CRLF and the BOM. The script files are Windows-authored, so tests use CRLF input.
- `LoadScriptFile` has a `file` drop-down built from `.txt`/`.md` files in the input folder (`_input_files`, recomputed when ComfyUI builds the node list, so **R** refreshes it) plus the **Choose file...** button, which uploads into that folder and selects the new name. `load` reads `<input folder>/<file>`, confined to the input folder through `realpath` and `commonpath` (the `path` output is the resolved full path). Having `file` in the `VALIDATE_INPUTS` signature makes ComfyUI skip the list-membership check, so files added after page load still validate; it rejects empty, placeholder and missing files. `IS_CHANGED` returns a path/mtime/size string, so the node re-runs when the file changes. There is no free path input.
