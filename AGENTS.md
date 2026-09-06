# AGENTS.md — Agent Runbook: Modal × ComfyUI × MiniMax-H3 Motion Director

This file is auto-loaded by agent harnesses (Cline, Claude Code, Codex,
Hermes-Agent, OpenCode, Antigravity, pi, …) when working in this repo. It is
the complete runbook for standing up and driving this app. Read it fully
before doing anything.

## What this project is

A serverless [Modal](https://modal.com) app that runs headless
[ComfyUI](https://github.com/comfyanonymous/ComfyUI) with the
[MiniMax H3 Motion Director](https://github.com/j955229/ComfyUI-MiniMax-H3-Motion-Director)
custom node (v1.2.0) on an **H200 GPU**. Users then open the ComfyUI web UI in
a **browser** and produce multi-segment video with the Director's timeline:

| Piece | What it is | Where it runs |
|---|---|---|
| `comfyui_director_serve.py` | ComfyUI 0.34+ + Motion Director custom node | Modal H200 |
| `scripts/smoke_director.py` | Health + node-registration smoke test | local (any machine) |
| Modal Volume `comfy-models` | MiniMax-H3 weights + rendered outputs | Modal (persistent) |

**No LLM. No model provider. Pure ComfyUI** — the Director node does all
T2V / I2V / FL2V / R2V / V2V / RV2V / Mixed-mode orchestration itself. The
user drives it from a browser; agents deploy, verify, and fetch outputs.

## HARD RULES (never violate)

1. **USER-SELECTED MODEL SET — NEVER replace or add to it.** The only
   MiniMax-H3 files (from `Comfy-Org/MiniMax-H3` on HF) are the 5 entries in
   `PATTERNS` inside `comfyui_director_serve.py`: fl2va bf16 (66.3 GB),
   ref2va int8 convrot (34.0 GB), qwen3vl_32b text encoder bf16 (51.5 GB —
   this is H3's own text encoder, NOT a separately served LLM), video vae
   fp16 (5.2 GB), audio vae fp32 (0.6 GB). **No turbo LoRAs, no other
   variants, ever.** Base mode only: 20 steps.
2. **Never commit `.env` or any token.** `.env` is gitignored;
   `.env.example` is committed. Never print secret values — check names only.
3. **Use `uv` for all Python envs** (never pip directly for venvs, never conda).
4. **HF transfer backend = Xet** (`HF_XET_HIGH_PERFORMANCE=1`, already set in
   the image). Never use `HF_HUB_ENABLE_HF_TRANSFER` (deprecated).
5. **`@app.server()` MUST decorate a CLASS** (Modal 1.5.x). Validate locally:
   `uv run --with "modal>=1.5.2,<1.6" python -c "import comfyui_director_serve"`.
6. **Do NOT install `ComfyUI-H3-Motion-Context`** alongside Motion Director —
   Motion Context is integrated into it; both at once = conflicts.
7. **Motion Director is UI-driven.** Mixed timelines, Segment Results, and the
   Material Library live in its browser panel. There is no supported
   "headless timeline JSON" path. Plain workflows still work via the
   `/prompt` API (that is how the T2V smoke test works).
8. **Verify latest versions against live sources** (Firecrawl or the live

## Architecture

```
   you / your agent ──deploy──▶ Modal App "comfyui-director-serve"
                                  │  H200 GPU (141 GB), ComfyUI 0.34+
                                  │  /workflow = ComfyUI source (image layer)
                                  │    └─ custom_nodes/ComfyUI-MiniMax-H3-Motion-Director
                                  │  /ComfyUI = Modal Volume "comfy-models"
                                  │    ├─ models/   (157 GB MiniMax-H3 set, downloaded
                                  │    │             at FIRST container start via Xet)
                                  │    └─ outputs/  (rendered videos persist here)
                                  ▼
                 HTTPS endpoint https://<ws>--comfyui-director-serve-....modal.direct
                                  │
              ┌───────────────────┴────────────────────┐
              ▼                                        ▼
   BROWSER (primary): full ComfyUI      AGENT (secondary): /system_stats,
   canvas + Director timeline panel     /object_info, /prompt, /history, /view
```

Why this shape: the Director's whole value is its interactive timeline UI, so
the app serves the full ComfyUI web UI over the Modal HTTPS endpoint. Agents
verify health and node registration over HTTP and fetch outputs from the
volume; humans (or browser-driving agents) operate the Director panel.

## Prerequisites (new machine)

- macOS or Linux, `uv`, `ffmpeg` (Node optional)
- Modal CLI: `uv tool install modal`; auth via `modal token new`
- A HuggingFace token (read access to `Comfy-Org/MiniMax-H3`)

## Full setup (in order — do not skip verification)

### 0. Environment

```bash
git clone https://github.com/techcwbldr26/Modal-ComfyUI-MiniMax-H3-Motion-Director-App.git
cd Modal-ComfyUI-MiniMax-H3-Motion-Director-App
cp .env.example .env            # fill MODAL_TOKEN_ID, MODAL_TOKEN_SECRET, HF_TOKEN
uv venv .venv
uv pip install --python .venv/bin/python "modal>=1.5.2,<1.6" huggingface_hub
modal profile current           # must show YOUR intended account
set -a; source .env; set +a
modal secret create huggingface-token HF_TOKEN="$HF_TOKEN"   # once per workspace
```

### 1. Deploy (~1 min image build; first container start +~20–40 min for weights)

```bash
modal deploy comfyui_director_serve.py 2>&1 | tee deploy_director.log
# copy the printed URL into .env → DIRECTOR_URL
```

**IMPORTANT:** the first request after deploy triggers the ~157 GB weight
download into the volume (Xet). Allow 20–40 minutes and watch
`modal app logs comfyui-director-serve`. Every later cold start skips it.

### 2. Verification gates (all must pass)

## Operations

### What agents must know

1. **The app auto-scales down after 15 min idle** — no restart needed; the
   next request cold-starts (~1–2 min with weights on the volume, then several
   minutes to load ~118 GB into VRAM on the first generation).
2. **Cost** — H200 ≈ $0.001261/s (~$4.54/h) per running container. When done:
   `modal app stop comfyui-director-serve -y`. Check spend:
   `modal billing report --for "this month"`.
3. **Outputs land on the volume**, not your machine. Fetch:
   `modal volume get comfy-models outputs/<file> ./`
4. **Health/read-only checks are agent-safe:** `GET /system_stats`,
   `GET /object_info`, `GET /history/<id>`. Starting generations (`POST
   /prompt`) costs GPU money — only do this when the user asked for it.

## Pitfalls (hard-won — do not repeat)

1. **`cannot mount volume on non-empty path`** — never `mkdir /ComfyUI` in the
   image build; the volume mounts there.
2. **ComfyUI repo ships a real `models/` dir** — the image build does
   `rm -rf /workflow/models` BEFORE symlinking to the volume; don't remove
   that step or ComfyUI scans empty dirs ("value not in list" errors).
3. **Weights download at RUNTIME, not build time** — build-time download of
   157 GB dies on the build sandbox (disk limits). `_ensure_models()` in
   `ComfyUIDirectorServer.start` is the proven pattern; leave it alone.
4. **Director UI looks broken after a redeploy** — hard-refresh the browser
   (Cmd+Shift+R); stale cached `web/js` assets.
5. **V2V/RV2V source video is browser-upload only** — Material Library videos
   are references, not source inputs.
6. **No `timeout` command on macOS** — use Python deadline loops (see
   `scripts/smoke_director.py`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `503 no upstreams` on first curl | Normal cold start — retry for a few minutes. |
| Director node missing in UI | Custom node import failed — run `scripts/smoke_director.py`, then `modal app logs comfyui-director-serve` for the traceback. |
| `Workflow fails: value not in list (model name)` | Model file not on volume — `modal volume ls comfy-models models/diffusion_models`. |
| Smoke test timeout | First run loads models into VRAM (~118 GB); allow several minutes, then re-run. |
| Token validation failed from modal CLI | Stale `MODAL_TOKEN_ID/SECRET` env vars override the profile — `unset` them. |
| Slow first generation | Normal — 66 GB UNET + 51.5 GB text encoder loading into VRAM. |

## Files

```
comfyui_director_serve.py   Modal app: ComfyUI + Motion Director on H200 (class-based @app.server)
scripts/smoke_director.py   /system_stats + /object_info smoke test (stdlib only)
scripts/smoke_t2v.py        end-to-end T2V proof — real MP4 via /prompt API
workflows/minimax_h3_t2v.json  official T2V template (UI format, converted in-script)
PROMPT_AUTHORING_GUIDE.md   how to author video prompts for the Director (READ before generating)
SETUP_PROMPT.md             self-contained paste-prompt for a fresh AI chat to do this setup
README.md                   human walkthrough
GOTCHAS.md                  quick pitfalls list
PLAN.md                     build plan + verification results
.env.example                secret & endpoint names (never commit .env)
```

## Notes for specific harnesses

- **Cline / Claude Code / Codex / OpenCode / Antigravity / pi:** this file is
  your runbook. Validate locally with the `uv run --with modal …` import
  check before any deploy; deploy only when the user asks; never print
  secrets.
- **Hermes-Agent:** no Hermes wiring is needed for this app — there is no LLM
  endpoint to register. If the user wants voice/chat-driven generation, they
  can point any MCP ComfyUI tool at `$DIRECTOR_URL`, but the Director
  timeline itself is browser-driven (see HARD RULE #7).


```bash
curl -s "$DIRECTOR_URL/system_stats" | grep -o 'NVIDIA H200'          # GPU up
uv run python scripts/smoke_director.py --url "$DIRECTOR_URL"          # → SMOKE-DIRECTOR-OK
```

`SMOKE-DIRECTOR-OK` proves: `/system_stats` healthy, ComfyUI ≥ 0.30.0, and all
three Director nodes (`MiniMaxH3MotionDirector`, `MiniMaxH3MotionDirectorInputs`,
`MiniMaxH3MotionDirectorAssets`) registered in `/object_info`.

Optional end-to-end proof (real MP4 via the `/prompt` API; costs GPU minutes):

```bash
uv run python scripts/smoke_t2v.py --url "$DIRECTOR_URL"   # downloads the MP4 to outputs/
```

### 3. Use it (browser)

Open `https://<ws>--comfyui-director-serve-....modal.direct` → double-click the
canvas → add the **"MiniMax H3 Motion Director"** node → pick a mode → add
Prompt Groups → Run. See `README.md` for the walkthrough and
`PROMPT_AUTHORING_GUIDE.md` before writing any video prompts.

   pages) before pinning anything. LLM training cutoffs are 6–12 months stale.
9. **Custom-node import failures are silent** — after ANY image change, run
   `scripts/smoke_director.py`; if the 3 Director nodes vanish from
   `/object_info`, grep `modal app logs comfyui-director-serve`.
