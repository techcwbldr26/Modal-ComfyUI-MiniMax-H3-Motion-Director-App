# GOTCHAS — ComfyUI-MiniMax-H3-Motion-Director on Modal

Hard-won rules for this app.

1. **Motion Director is UI-driven.** Mixed-mode timelines, Segment Results, and
   the Material Library live in the Director panel (web/js frontend + PromptServer
   HTTP routes). There is no supported "headless timeline JSON" path — drive it
   from a browser at the Modal URL. The `/prompt` API still works for plain
   workflows (that's what standard ComfyUI API tests use).
2. **Do NOT install ComfyUI-H3-Motion-Context** in custom_nodes alongside Motion
   Director — Motion Context is integrated; both at once = conflicts.
3. **Custom node import failures are silent.** ComfyUI keeps serving even if the
   Director fails to import; the nodes just vanish. Always check
   `scripts/smoke_director.py` (asserts the 3 node classes in `/object_info`)
   after any image change, and grep `modal app logs comfyui-director-serve` for
   `ComfyUI-MiniMax-H3-Motion-Director` import errors.
4. **Custom node frontend changes need a hard refresh.** After redeploying the
   image, hard-refresh the browser (Cmd+Shift+R) — stale cached web/js assets
   otherwise show a broken Director panel.
5. **First cold start after deploy loads ~118 GB into VRAM** (66 GB fl2va UNET +
   51.5 GB text encoder) — allow several minutes before judging a timeout.
   For long Mixed-mode runs, enable the Director's **Clear VRAM Between
   Segments** (releases models between segments; slower but stabler).
6. **One volume = one source of truth.** All weights and outputs live on the
   `comfy-models` Modal Volume mounted at `/ComfyUI`. If you run other
   ComfyUI-on-Modal apps, reuse the same volume name to share the downloaded
   weights — normal concurrent use is fine (containers only read the weights).
7. **V2V/RV2V source video is local-upload only** (browser upload through the
   Director UI). Material Library videos are references, not source inputs.
8. **Cost discipline:** H200 ~$4.54/h per running container. The Director
   session keeps the container alive as long as you keep generating; when done:
   `modal app stop comfyui-director-serve -y`.

