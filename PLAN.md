# PLAN.md — Modal × ComfyUI × MiniMax-H3 Motion Director (no LLM)

All sources verified live 2026-09-06 via Firecrawl (repo README, `__init__.py`,
`requirements.txt`, USER_GUIDE.md).

**What this is:** the [ComfyUI-MiniMax-H3-Motion-Director](https://github.com/j955229/ComfyUI-MiniMax-H3-Motion-Director)
custom node (v1.2.0, GPL-3.0) running inside headless ComfyUI on a Modal H200.
Model weights live on the `comfy-models` Modal Volume (~157 GB, downloaded at
first container start).

## Deliverables

| File | Purpose |
|---|---|
| `comfyui_director_serve.py` | Modal app: ComfyUI master + Motion Director custom node on H200 |
| `scripts/smoke_director.py` | Health + version gate + asserts the 3 Director nodes in `/object_info` |
| `README.md` | Setup + browser usage walkthrough |
| `GOTCHAS.md` | Pitfalls specific to this app |
| `.env.example` | Modal keys + HF_TOKEN only (no LLM vars) |

## Steps

1. **Local validation ($0):**
   `uv run --with "modal>=1.5.2,<1.6" python -c "import comfyui_director_serve"`
   (must not raise — class-based `@app.server()` is a Modal 1.5.x requirement).
2. **Deploy:** `modal deploy comfyui_director_serve.py` (image build only, ~1 min;
   the first container start downloads ~157 GB of weights into the volume, 20–40 min).
3. **Verify:**
   - `curl -s "$DIRECTOR_URL/system_stats"` → NVIDIA H200, comfyui_version ≥ 0.30.0
   - `uv run python scripts/smoke_director.py --url "$DIRECTOR_URL"` → SMOKE-DIRECTOR-OK
4. **Use:** open `https://<ws>--comfyui-director-serve-....modal.direct` in a
   browser → double-click canvas → add **"MiniMax H3 Motion Director"** → build.
5. **Idle hygiene:** `modal app stop comfyui-director-serve -y`.

## Verification gates (all verified 2026-09-06)

- [x] import check passes (Step 1)
- [x] `/object_info` contains `MiniMaxH3MotionDirector`, `MiniMaxH3MotionDirectorInputs`, `MiniMaxH3MotionDirectorAssets`
- [x] ComfyUI 0.34.0 serving on NVIDIA H200 (`/system_stats`)
- [x] end-to-end T2V generation produced a real MP4 through the `/prompt` API
- [x] Director node visible + usable in the browser UI
