# ComfyUI-Shots-Parser

Two small ComfyUI nodes (standard library only, no extra packages) that replace the "20 shot slots" part of the MiniMax H3 workflow.

| Node | What it does |
|---|---|
| **Load Script File** | Like core *Load Image*: a drop-down of `.txt` / `.md` files in `ComfyUI/input` (3 folder levels deep). Added a file? Press **R** in the UI to refresh the list. Or type any full path into **path_override** and no list is involved. Outputs `text` (CRLF -> LF, BOM removed, UTF-8 with GBK fallback) and the resolved `path`. Re-reads the file on every run if it changed. |
| **Shot Script Parser** | One pass over the script: finds every `### SHOT n` block, takes the `PROMPT:` text, builds the `start-end: prompt` lines the NG Director expects, and computes the film length from the shots it actually parsed. |

Parser outputs: `shots` (STRING), `shot_count` (INT), `project_seconds` (FLOAT), `chunk_seconds` (FLOAT), `report` (STRING, send to a Preview Any).
Wire `shots` -> Director `shots`, `project_seconds` -> `project_seconds`, `chunk_seconds` -> `chunk_seconds`.

## Install
Pick one, then restart ComfyUI. Nothing to pip install. Nodes appear under category **ShotScript**.

1. **ComfyUI-Manager** (git URL): open Manager -> **Install via Git URL** and enter `https://github.com/shubin73/ComfyUI-Shots-Parser`.
2. **git clone**:
   ```
   cd ComfyUI/custom_nodes
   git clone https://github.com/shubin73/ComfyUI-Shots-Parser
   ```
3. **Manual**: copy (or symlink) this folder to `ComfyUI/custom_nodes/ComfyUI-Shots-Parser`.

To update, run `git pull` inside the folder (or use Manager's update button), then restart ComfyUI.

To run the example workflow you also need the [ComfyUI-MiniMaxH3-Director](https://github.com/seesee75-commits/ComfyUI-MiniMaxH3-Director) pack; see [Requirements for the example workflow](#requirements-for-the-example-workflow).

## Example workflow
`example_workflows/minimax_h3_video_generation_multi_shots_script.json` is the MiniMax H3 workflow with the 20 shot slots replaced by Load Script File -> Shot Script Parser -> NG Director. It also appears in ComfyUI's template browser. Copy `example_workflows/sample_scripts.txt` into `ComfyUI/input` and press **R** to load the sample script.

### Requirements for the example workflow
The two nodes in this pack need nothing else. The example workflow also uses nodes from elsewhere:

| Nodes | Provided by |
|---|---|
| NG Context Image (`NGContextImage`), NG Director (`NGDirector`), NG Render Sequence (`NGRenderSequence`) | **[ComfyUI-MiniMaxH3-Director](https://github.com/seesee75-commits/ComfyUI-MiniMaxH3-Director)** (registry name `minimaxh3-director`, GPL-3.0). Install it from ComfyUI-Manager (search "MiniMax H3 Director") or from the repo, then `pip install -r requirements.txt` (OpenCV). It needs ComfyUI 0.37 or newer. |
| Load Diffusion Model, Load CLIP, Load VAE, LoRA Loader (model only), Save Video, Preview Any, Primitive (Int / String / String Multiline / Boolean), Switch, Resolution Selector | ComfyUI core (no custom pack) |

Models (not bundled, put them in the usual `ComfyUI/models` folders): the MiniMax H3 Ref2VA diffusion model, a CLIP of type `minimax`, the H3 video VAE and audio VAE, and optionally the H3 turbo LoRA. Choose the files you have in the loader nodes. See the [MiniMax H3 model page](https://huggingface.co/Comfy-Org/MiniMax-H3).

Missing nodes show up red when you open the workflow. ComfyUI-Manager's **Install Missing Custom Nodes** finds the pack for you.

## Script format (your current format works unchanged)
```
### SHOT 1: Title (0:00 - 0:08)
CONTINUOUS: NO
PROMPT: text of the shot ...

### SHOT 2: Title (0:08 - 0:16)
CONTINUOUS: YES
PROMPT: ...
```
* A marker is `###` + `SHOT` + number at the **start of a line** (`SHOT 1`, `SHOT 01`, `###SHOT 1` all fine). A sentence that merely mentions "### SHOT n" is not a shot.
* `PROMPT:` is required and runs to the next marker (multi-line prompts are joined into one line). `CONTINUOUS:` is optional.
* `<Picture 1>` becomes `@pic1` (any number; switch off with `picture_alias`). It must match the **name** of a Context card in the Director (the example uses `pic1`...`pic4`); the Director then writes the label H3 expects (`<Subject N>` for a character, `<Picture N>` for a frame or place). Do not write `<Image 1>`: H3 has no such label.
* The `(m:ss - m:ss)` in the header is only used for a warning when it differs from `shot_seconds`.

## What it fixes
* **Phantom shots**: film length = parsed shots x `shot_seconds`. The old graph counted the characters `### SHOT` anywhere in the file (a guide comment or a half-written header added a shot) and extracted prompts with a separate regex, so the two could disagree.
* **Fail fast** (`strict` ON): a half-written shot, duplicate number, missing PROMPT, more shots than `max_shots`, or a shot longer than `max_shot_seconds` stops the run with a clear message **before** any rendering. OFF = report and carry on with what parsed.
* **No time gaps**: shots 1 and 3 render back to back (`0-15`, `15-30`), not `0-15` and `30-45`.
* **No stray carriage returns** from Windows line endings.
* 120 slot nodes (+ counting and cleanup) become 2 nodes.

## Not covered yet
* All shots still share one length (`shot_seconds`), because the NG Director plans equal parts (parts = project / chunk). The parser already reads each header's time range, so per-shot lengths would need a Director (or a grain/one-shot-per-run design) that accepts them.
* `CONTINUOUS:` is parsed (shown in the report) but nothing downstream uses it.

## Tests
`python3 -I -m unittest discover -s tests -v` (21 tests: your real script, CRLF, phantom-shot cases, id gaps, stale file list, GBK fallback, strict mode). The ComfyUI side is tested with a stub of `folder_paths`; it has **not** been run inside a real ComfyUI.
