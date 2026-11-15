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
- `nodes.py` is a thin ComfyUI wrapper and imports `folder_paths`, which only exists inside ComfyUI. `__init__.py` registers the node mappings.
- `nodes.py` imports the parser with a relative import (`from .shot_parser import ...`), so it only works when loaded as a package. The tests import `shot_parser` directly (`sys.path` insert), and they exercise `nodes.py` through a stubbed `folder_paths` module. The nodes have not been run in a real ComfyUI.

## Behaviors to preserve

- **Film length is derived from the parsed shots**: `total_seconds = shot_seconds * len(shots)`. Never count markers separately from the parsed shots. That mismatch was the "phantom shot" bug this package exists to fix.
- **Time is packed back to back.** Gaps in shot ids do not create empty time. All shots share one length (`shot_seconds`), because the Director plans equal parts. Per-shot header ranges are only used for a warning.
- **Strictness is in the node, not the parser.** The parser collects `errors` and never raises. `ShotScriptParser.parse` raises `ValueError` when `strict` is on, so a bad script fails before any rendering.
- `normalize_newlines` strips CRLF and the BOM. The script files are Windows-authored, so tests use CRLF input.
- `LoadScriptFile` has a custom `VALIDATE_INPUTS`. Having `file` in its signature makes ComfyUI skip the dropdown membership check, so files added after page load still validate. `IS_CHANGED` returns a path/mtime/size string, so the node re-runs when the file changes. Paths in the `file` dropdown are confined to the input folder through `realpath` and `commonpath`. `path_override` is deliberately unrestricted.
