"""ComfyUI nodes: Load Script File + Shot Script Parser."""
from __future__ import annotations

import os

import folder_paths  # provided by ComfyUI

from .shot_parser import normalize_newlines, parse_script

TEXT_EXTS = (".txt", ".md")
MAX_BYTES = 2_000_000
NO_FILES = "[no .txt/.md files in the input folder]"


def _input_files() -> list[str]:
    """Text files under ComfyUI/input (3 folder levels deep), like core Load Image lists images.
    Recomputed every time ComfyUI builds the node list, so press R in the UI after adding a file."""
    base = folder_paths.get_input_directory()
    found = []
    for root, dirs, files in os.walk(base):
        rel = os.path.relpath(root, base)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= 3:
            dirs[:] = []
        for name in files:
            if name.lower().endswith(TEXT_EXTS):
                found.append(os.path.relpath(os.path.join(root, name), base).replace(os.sep, "/"))
    return sorted(found)


def _resolve(file: str, path_override: str) -> str:
    override = (path_override or "").strip().strip('"').strip("'")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    base = os.path.realpath(folder_paths.get_input_directory())
    full = os.path.realpath(os.path.join(base, file))
    if os.path.commonpath([base, full]) != base:
        raise ValueError("file must be inside the input folder")
    return full


def _read(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"file is larger than {MAX_BYTES} bytes")
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("file is not UTF-8 (or GBK/GB18030) text")


class LoadScriptFile:
    """Load a text script from the input folder (like Load Image) or from any typed path."""

    @classmethod
    def INPUT_TYPES(cls):
        files = _input_files() or [NO_FILES]
        return {
            "required": {
                "file": (files, {"tooltip": "Text files in ComfyUI/input (also sub-folders). "
                                            "Added a file? Press R in the UI to refresh this list."}),
            },
            "optional": {
                "path_override": ("STRING", {"default": "", "multiline": False,
                                             "tooltip": "Optional full path to a .txt/.md file anywhere on this "
                                                        "computer. When filled in, it is used instead of 'file' "
                                                        "and no list refresh is needed."}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "path")
    FUNCTION = "load"
    CATEGORY = "ShotScript"
    DESCRIPTION = "Reads a UTF-8 text file (.txt/.md) from the input folder or a typed path."

    @classmethod
    def IS_CHANGED(cls, file, path_override=""):
        try:
            p = _resolve(file, path_override)
            st = os.stat(p)
            return f"{p}|{st.st_mtime_ns}|{st.st_size}"
        except Exception:
            return "missing"

    @classmethod
    def VALIDATE_INPUTS(cls, file, path_override=""):
        # having 'file' in the signature skips ComfyUI's list check, so files added after the page was
        # loaded still validate
        try:
            p = _resolve(file, path_override)
        except ValueError as e:
            return str(e)
        if file == NO_FILES and not (path_override or "").strip():
            return "No script selected: put a .txt in ComfyUI/input and press R, or fill in path_override."
        if not os.path.isfile(p):
            return f"File not found: {p}"
        if not p.lower().endswith(TEXT_EXTS):
            return f"Only {', '.join(TEXT_EXTS)} files are accepted: {p}"
        return True

    def load(self, file, path_override=""):
        p = _resolve(file, path_override)
        return (normalize_newlines(_read(p)), p)


class ShotScriptParser:
    """Turn a '### SHOT n' script into the 'start-end: prompt' text the NG Director expects."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "script": ("STRING", {"multiline": True, "default": ""}),
                "first_shot_id": ("INT", {"default": 1, "min": 0, "max": 9999,
                                          "tooltip": "Shots numbered below this are ignored."}),
                "shot_seconds": ("INT", {"default": 15, "min": 1, "max": 600,
                                         "tooltip": "Length of every shot (all shots share it)."}),
                "max_shot_seconds": ("INT", {"default": 15, "min": 0, "max": 600,
                                             "tooltip": "Longest part the model can render; 0 = no check."}),
            },
            "optional": {
                "max_shots": ("INT", {"default": 0, "min": 0, "max": 9999,
                                      "tooltip": "Stop if the script has more shots than this; 0 = no limit."}),
                "picture_alias": ("BOOLEAN", {"default": True,
                                              "tooltip": "Rewrite '<Picture 1>' to '@pic1' in the prompts."}),
                "strict": ("BOOLEAN", {"default": True,
                                       "tooltip": "ON: any problem stops the run BEFORE rendering. "
                                                  "OFF: report problems and carry on with what parsed."}),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("shots", "shot_count", "project_seconds", "chunk_seconds", "report")
    FUNCTION = "parse"
    CATEGORY = "ShotScript"
    DESCRIPTION = ("Finds every '### SHOT n' block in one pass. Film length = shots parsed x shot_seconds, "
                   "so the count can never disagree with the shot text.")

    def parse(self, script, first_shot_id, shot_seconds, max_shot_seconds,
              max_shots=0, picture_alias=True, strict=True):
        res = parse_script(script, first_shot_id=first_shot_id, shot_seconds=shot_seconds,
                           max_shot_seconds=max_shot_seconds, max_shots=max_shots,
                           picture_alias=picture_alias)
        if strict and res.errors:
            raise ValueError("Shot script problems (nothing was rendered):\n- " + "\n- ".join(res.errors)
                             + "\n\n" + res.report)
        return (res.shots_text, res.shot_count, res.total_seconds, res.chunk_seconds, res.report)
