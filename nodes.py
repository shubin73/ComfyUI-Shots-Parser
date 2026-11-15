"""ComfyUI nodes: Load Script File + Shot Script Parser."""
from __future__ import annotations

import os

import folder_paths  # provided by ComfyUI

from .shot_parser import normalize_newlines, parse_script

TEXT_EXTS = (".txt", ".md")
MAX_BYTES = 2_000_000
NO_FILES = "[no .txt/.md files yet: click Choose file...]"


def _input_files() -> list[str]:
    """Text files under ComfyUI/input (3 folder levels deep), like core Load Image lists images.
    Recomputed every time ComfyUI builds the node list, so press R in the UI after adding a file by hand."""
    base = input_folder()
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


def input_folder() -> str:
    return os.path.realpath(folder_paths.get_input_directory())


def _resolve(file: str) -> str:
    """The script file is always inside the input folder (that is where 'Choose file...' puts it)."""
    base = input_folder()
    full = os.path.realpath(os.path.join(base, (file or "").strip()))
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


def save_upload(filename: str, data: bytes) -> str:
    """Store an uploaded script in the input folder and return its name there (what the 'file' field shows).
    Only the base name is used, only .txt/.md, never replaces a different file: a name clash gets ' (1)'."""
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    if not name or name.startswith(".") or not name.lower().endswith(TEXT_EXTS):
        raise ValueError(f"Only {', '.join(TEXT_EXTS)} files are accepted.")
    if len(data) > MAX_BYTES:
        raise ValueError(f"file is larger than {MAX_BYTES} bytes")
    base = input_folder()
    os.makedirs(base, exist_ok=True)
    stem, ext = os.path.splitext(name)
    n = 0
    while True:
        candidate = name if n == 0 else f"{stem} ({n}){ext}"
        dest = os.path.join(base, candidate)
        if not os.path.exists(dest):
            break
        with open(dest, "rb") as f:
            if f.read(MAX_BYTES + 1) == data:           # same file uploaded again: reuse it
                return candidate
        n += 1
    with open(dest, "wb") as f:
        f.write(data)
    return candidate


class LoadScriptFile:
    """Pick a text script from the input folder, or add one with the 'Choose file...' button (js/load_script_file.js)."""

    @classmethod
    def INPUT_TYPES(cls):
        files = _input_files() or [NO_FILES]
        return {
            "required": {
                "file": (files, {"tooltip": "Text files in ComfyUI/input (also sub-folders). Not listed? "
                                            "Click Choose file... to add one, or press R to refresh the list."}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "path")
    FUNCTION = "load"
    CATEGORY = "ShotScript"
    DESCRIPTION = "Pick a UTF-8 .txt/.md script from the list, or add one with 'Choose file...'; outputs its text and full path."

    @classmethod
    def IS_CHANGED(cls, file):
        try:
            p = _resolve(file)
            st = os.stat(p)
            return f"{p}|{st.st_mtime_ns}|{st.st_size}"
        except Exception:
            return "missing"

    @classmethod
    def VALIDATE_INPUTS(cls, file):
        # having 'file' in the signature skips ComfyUI's list check, so files added after the page was
        # loaded still validate
        if not (file or "").strip() or file == NO_FILES:
            return "No script selected: pick one in the list or click 'Choose file...' on the Load Script File node."
        try:
            p = _resolve(file)
        except ValueError as e:
            return str(e)
        if not os.path.isfile(p):
            return f"File not found in the input folder: {file}. Click 'Choose file...' again."
        if not p.lower().endswith(TEXT_EXTS):
            return f"Only {', '.join(TEXT_EXTS)} files are accepted: {file}"
        return True

    def load(self, file):
        p = _resolve(file)
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
