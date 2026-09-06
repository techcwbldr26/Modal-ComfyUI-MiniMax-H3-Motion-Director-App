# PROMPT_AUTHORING_GUIDE.md — Authoring prompts for the MiniMax H3 Motion Director

**Audience:** the LLM (or human) that authors storyboard reference panels and
the per-segment video prompts entered into the Motion Director's Prompt
Groups, in this Modal × ComfyUI × MiniMax-H3 Motion Director app.

**Purpose:** this file exists because the first production runs of MiniMax-H3
surfaced real, repeatable failures in how references and prompts were
authored. Follow these instructions exactly so a first run produces clean
videos with zero iteration.

---

## 1. What went wrong in production (2026-08-21) — learn from this

### 1.1 The squished contact-sheet morph (the big one)

Storyboard reference sheets were **6-panel contact sheets** (a 2×3 grid of
separate scene images on one canvas). When the video model was given the
**whole sheet** as its start image / reference, it did not "zoom into" one
panel — it reproduced the **entire squished grid** for the first ~2.5 seconds
(a "contact-sheet morph"), then slowly resolved into a clean shot.

**Root cause:** the video model treats the first frame as a literal scene. A
grid of six tiny images is not a scene — it is a collage, and the model
faithfully animates the collage.

**The fix that works in this app:** split the sheet into standalone panels
first (any 2×3 cropper; e.g. Pillow or
`uv run --with pillow python scripts/split_contact_sheet.py <sheet> panels/ --grid 2x3`
if you have it), then upload **one standalone panel** per slot in the
Director — as the segment's start image (I2V/FL2V), or as a Common Reference
/ Segment Local Asset (R2V). NEVER upload the full sheet.

### 1.2 Unnumbered panels = guesswork

Because panels had no numbers, the author had to *guess* which panel matched
which storyboard beat. This caused wrong panels chosen as start images,
ambiguous prompts, and wasted GPU time on re-runs. **Number every panel**
inside the panel (top-left) so each survives cropping.

### 1.3 Model-set constraints were not in the prompt

Prompts must state the hard model rules up front (base mode = 20 steps, no
turbo LoRA, only the 5 user-selected model files exist). Otherwise an agent
discovers them mid-run.

### 1.4 No explicit frame math

"8 seconds" is not a valid MiniMax-H3 length. The frame grid is **17k + 5
frames**. 8 s @ 24 fps = 192 frames = 17×11+5 ✓. Every segment's prompt must
state the frame math; every Prompt Group's Duration must land on the grid.

### 1.5 Hallucinated characters (the worst failure)

A video contained **extra figures** (a suited man, a cartoon cat) that exist
nowhere in the reference panels — invented from loose phrasing.

**Rule:** the video must contain ONLY the characters that appear in the
reference panels and the prompt. No additional figures, no "background
characters". If the prompt does not name a character, they do not exist.

### 1.6 Art-style drift (photoreal → cartoon)

References were 100% photoreal; the video rendered the characters as cartoons

### 2.3 Model-set constraints — include verbatim in the prompt packet

```
HARD RULES: base mode only — 20 steps, NO turbo LoRA. The installed model set
is fixed (minimax_h3_fl2va_bf16 / minimax_h3_ref2va_int8_convrot +
qwen3vl_32b text encoder + both VAEs) — never request other variants.
References are numbered STANDALONE panels — NEVER a whole contact sheet.
ONLY the characters named in this prompt may appear — NO additional people,
animals, or background figures. Art style of every character MUST match the
reference panels exactly (photoreal reference = photoreal characters; do NOT
use words like "illustrated" or "cartoon" unless the references actually are).
```

### 2.4 Frame math — include in every segment prompt

```
<duration> seconds at 24fps = <N> frames (snap to the 17k+5 grid:
N = 17k + 5, k = ceil((duration*24 - 5) / 17)).
```

Examples: 1 s → **22 frames** · 5 s → **124 frames** · 8 s → **192 frames**.

### 2.5 Resolution

- The Director UI exposes aspect ratio + **Megapixels**; the native canvas is
  1344×768 (0.98 MP), 24 fps. Quick tests: ~0.2 MP (≈608×352).
- All dimensions are multiples of 32 (the UI computes them from megapixels).

### 2.6 Character-count lock

- Name every allowed character explicitly; end the prompt with: "ONLY these
  characters may appear — no additional people, animals, or background
  figures."

### 2.7 Style fidelity

- Copy style adjectives from the references. Photoreal refs → "photoreal" —
  never "illustrated", "cartoon", "semi-realistic" unless the refs are.

### 2.8 Cross-segment continuity (the Director's superpower)

- Later segments inherit state only if you say so: carry forward character
  pose, lighting direction, time of day, and camera position in each new
  segment's prompt.
- Prefer **Mixed Mode** with **Segment Result** reuse (a decoded frame from
  an earlier segment becomes a later I2V/FL2V start image) over pure T2V
  chains — it anchors identity far better.
- Leave boundary continuity controls (Motion Context / Color Re-anchor) ON
  for continuous scenes; disable when segments are intentionally separate
  shots.
- Continuity improves handoff but does NOT guarantee invisible boundaries —
  review every boundary before accepting.

---

## 3. Per-segment prompt packet (template)

For EACH Prompt Group / Mixed segment, author this packet:

```
SEGMENT <n> — MODE: <T2V | I2V | FL2V | R2V | Source Video>
DURATION: <d> seconds (17k+5 grid: <frames> frames)
START IMAGE / REFERENCES: standalone panel(s) <numbers> — never the sheet

PROMPT (enter into the Prompt Group):
<Cinematic prompt — see body template below. Repeat every character's
appearance + art style here; the Director does not inherit them.>

FRAME MATH: <d> seconds at 24fps = <N> frames (17k+5 grid).
RESOLUTION: <MP> MP, 16:9, multiples of 32.
```

**Prompt body template:**

```
Cinematic animation, <N> seconds. <Plate/reference style — copied from the
panels>.
<Camera>: <shot size, angle, movement>.
<Action>: <what happens — character A does X, character B does Y>.
<Character A>: <appearance — matches reference panel <X> exactly>.
<Character B>: <appearance — matches reference panel <Y> exactly>.
<Lighting & shadows>: <direction, quality, how shadows track>.
<Depth of field / grade / sound>: <lens look, color treatment, ambient audio>.
ONLY these characters may appear — no additional people, animals, or
background figures. Both characters must match their reference panels
exactly — <key likeness details> in particular.
```

---

## 4. Run order in the Director UI

1. Author the storyboard sheet (numbered 2×3 grid) → split into standalone
   panels → upload the needed panels to the **Material Library** (persistent)
   or directly per-segment.
2. Select the generation mode; add one Prompt Group per beat with its packet.
3. For multi-shot continuity, use **Mixed Mode**: pick each segment's method,
   set boundary continuity, reuse Segment Results as later start images.
4. Run. Watch **Live Preview**. Enable **Postprocess** only after the
   first-pass content is worth keeping.
5. Reroll failures with **Selective Run** (only the failed segments rerun —
   this is where good numbering + per-segment packets pay off).
6. **Results → Final Result** → save. Fetch from the volume:
   `modal volume get comfy-models outputs/<file> ./`

## 5. Checklist before you deliver any packet

- [ ] Every reference is a standalone numbered panel — never the full sheet
- [ ] One beat per Prompt Group / Mixed segment; durations on the 17k+5 grid
- [ ] HARD RULES block included (base mode, 20 steps, no turbo LoRA)
- [ ] Character-count lock included
- [ ] Style words match the reference panels EXACTLY
- [ ] FRAME MATH and RESOLUTION lines included
- [ ] Panel numbers named for every character pairing
- [ ] Cross-segment continuity carried forward in later prompts

because the prompt said "illustrated"/"semi-realistic".

**Rule:** the OUTPUT style must match the reference panels EXACTLY. Take
style adjectives FROM the reference material — never invent them.

---

## 2. HARD RULES for every prompt you author

### 2.1 Map each storyboard beat to one Director segment

- One beat = **one Prompt Group** (standalone modes) or **one Mixed segment**.
- Set each group's **Duration** to a 17k+5-grid-legal length.
- Do not cram two camera setups into one segment — split it.

### 2.2 References: standalone panels only

- I2V / FL2V: upload the numbered standalone panel as the segment's start
  image (FL2V can also take a LAST frame from a different panel).
- R2V / RV2V: identity/scene/prop references go in **Common References**
  (shared across segments) or the segment's **Local Assets**.
- Name the panel number in the prompt ("character A matches reference panel
  2 exactly") so a reviewer can verify the pairing.
