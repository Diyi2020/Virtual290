# Virtual290 — Real-Time Agentic Blackboard Lecturer for Math Papers

**Goal.** Feed in a mathematics paper; a virtual lecturer teaches it on a blackboard the way a good graduate course is taught — building the board up, keeping the theorem statement visible while proving it, pointing at the step being discussed, erasing when the board fills — and you can interrupt and ask questions at any time.

**Scope decisions (locked):**

| Axis | Decision |
|---|---|
| Purpose | Usable tool for you / the lab. Reliability and content quality over novelty. |
| Board | Programmatic rendering (KaTeX → SVG → animated canvas). Not video-gen, not stroke synthesis. |
| Character | Voice + simple 2D avatar with a pointing hand. Not photorealistic. |
| Interaction | Conversational, sub-2s to first response, barge-in supported. |

**Status — August 2026.** M0 (board spike) is **done and passed**. See `m0-board-spike.html` and §6b for what it settled and what it changed. Next milestone is the **compiler**, not ingestion — see §7. Target paper is fixed: [arXiv:2607.21798](https://arxiv.org/abs/2607.21798), §6c.

---

## 1. The central design tension, and how to resolve it

Good math exposition requires **planning ahead** — you cannot decide what to write in the top-left corner until you know what needs to stay visible for the next twenty minutes. Real-time conversation requires **reacting now**.

These fight each other. The resolution is a **two-phase architecture**:

```
┌──────────────────── OFFLINE (minutes, expensive, careful) ────────────────────┐
│  Paper → Semantic Graph → Lecture Plan → Board Script + Narration Script      │
└───────────────────────────────────────────────────────────────────────────────┘
                                    ↓ compiled artifact
┌──────────────────── ONLINE (milliseconds, cheap, reactive) ───────────────────┐
│  Presenter executes the script · Listens · Interrupts itself · Answers ·      │
│  Makes LOCAL board edits · Resumes                                            │
└───────────────────────────────────────────────────────────────────────────────┘
```

The offline compiler does all the hard thinking. The online presenter is mostly an *executor* with a narrow set of powers: it can pause, annotate, add a scratch derivation in the margin, jump to a different node of the plan, and resume. It is never asked to invent global board layout under a latency budget.

**Everything below follows from this split.**

---

## 2. The single most important artifact: the Board Instruction Language (BIL)

Before writing any AI code, define the typed interface between "the agent" and "the pixels." Every downstream decision gets easier once this exists.

**BIL v0.2** — revised after M0. The one structural change: a `write` op is no longer a LaTeX string plus separate commentary. It is a list of **`{tex, say}` chunks**, because real lecturers narrate what they write *while* writing it. See §6b.

```jsonc
// A board script is an ordered stream of ops. Each op is deterministic and replayable.

{ "op": "write",
  "id": "thm-3.1",                       // stable handle for later reference
  "role": "theorem",                     // theorem | definition | step | remark | scratch
  "persistence": "pinned",               // pinned | working | ephemeral
  "panel": 1,
  "pre":  "Here's the statement we're aiming at.",     // commentary before
  "chunks": [                            // glyphs for chunk k revealed while chunk k is spoken
    { "tex": "\\|T_n f - f\\|_{L^2}", "say": "the L two norm of T n f minus f" },
    { "tex": "\\to 0",                "say": "goes to zero" },
    { "tex": "\\quad (n \\to \\infty)","say": "as n goes to infinity" }
  ],
  "post": "So the operators converge strongly, not just weakly.",
  "provenance": { "kind": "verbatim", "ref": "§3.1, eq (7)" } }
  // RULE: every chunk must be independently well-formed LaTeX — chunk-level glyph
  // counts are what keep speech and handwriting in sync.

{ "op": "write",
  "id": "step-4",
  "chunks": [{ "tex": "= \\int_0^1 |\\hat f(\\xi)|^2 (1-\\rho_n(\\xi))^2 \\, d\\xi",
               "say": "equals the integral from zero to one of ..." }],
  "role": "step",
  "persistence": "working",
  "continues": "step-3",                 // aligns on the equals sign of the previous line
  "provenance": { "kind": "derived", "confidence": 0.82,
                  "note": "paper writes 'by Plancherel'; expansion is mine" } }

{ "op": "annotate", "target": "thm-3.1", "style": "box",       "color": "yellow" }
{ "op": "annotate", "target": "step-4",  "style": "underbrace", "span": [3, 7],
  "label": "\\text{this is the error term}" }
{ "op": "arrow",   "from": "def-2",  "to": "step-4", "label": "(2.1)" }
{ "op": "point",   "target": "step-4.span[3:7]", "hold_ms": 1800 }
{ "op": "erase",   "panel": 2, "keep": ["thm-3.1"] }
{ "op": "say",     "text": "So the whole thing collapses to the tail of the Fourier series.",
  "sync": "after:step-4" }               // narration ↔ board alignment anchor
{ "op": "wait_for_question", "timeout_ms": 3000 }
```

**Why this pays for itself:**

- The LLM never touches pixels. It emits validated JSON; a deterministic renderer draws it. Math is always typeset correctly.
- Board scripts are **diffable, replayable, seekable, and testable**. You can unit-test "was anything erased while still referenced?" without rendering a frame.
- Swappable back ends: canvas for live, Manim or headless-browser+ffmpeg for offline export, later maybe a real handwriting model — same script.
- Interruption handling becomes trivially expressible: *splice ops into the stream*, then resume.
- Evaluation becomes tractable (see §8).

**Build the BIL schema and its validator in week 1.** Everything else plugs into it.

---

## 3. Component breakdown

### 3.1 Ingestion — paper → structured source

Prefer **LaTeX source over PDF**, always. arXiv exposes it at `arxiv.org/e-print/<id>`.

1. `latexpand` to flatten multi-file projects into one.
2. `de-macro` (plus a custom pass) to expand author-defined macros — math papers are ~40% custom macros and every downstream stage breaks without this.
3. Parse with **plasTeX** (better at diverse `\newtheorem` environments) or **LaTeXML** (better XML/MathML fidelity). Run both, prefer plasTeX, fall back on failure.
4. **PDF fallback path** for non-arXiv papers: layout model + VLM math OCR. Treat as degraded mode — warn the user that provenance is less reliable.

Output: a normalized document tree with theorem environments, numbered equations, cross-references, and figures resolved.

### 3.2 Semantic graph — the paper's knowledge base

Turn the document tree into a typed graph. This is both the input to the lecture planner **and** the retrieval index for real-time Q&A.

- **Nodes:** `Notation`, `Definition`, `Assumption`, `Lemma`, `Theorem`, `Proof`, `ProofStep`, `Example`, `Equation`, `Figure`, `Remark`.
- **Edges:** `uses`, `proves`, `specializes`, `cites`, `defined_before`, `contradicts_if_dropped`.
- **Extraction:** rule-based where LaTeX structure gives it to you free (`\label`/`\ref`, theorem environments, `\cite`); LLM where it doesn't (which lemma does step 4 actually invoke? what does "clearly" hide?).
- **Notation table:** every symbol introduced, where, and what it means. Non-negotiable — half of real-time questions are "wait, what's $\rho_n$ again?" and this makes them a sub-100ms lookup instead of an LLM call.

### 3.2b Prerequisite layer and adaptive depth *(added at M1)*

A frontier paper's semantic graph must model not only what the paper contains but **what it presupposes and never defines**. For arXiv:2607.21798 that's Lindbladians, Gibbs states, Davies generators, spectral gap/mixing, mean-field Heisenberg, Schur–Weyl, symmetry breaking. This is most of what makes a lecture better than the PDF.

But a listener's background varies enormously, and teaching a quantum information researcher what a Lindbladian is wastes their afternoon. So prerequisite blocks are **optional and depth-adaptive**. Each block is authored at three depths:

| Depth | What it is | When |
|---|---|---|
| `full` | The real explanation, 1–3 min | Listener doesn't know it |
| `brief` | 20–30s refresher, notation plus the one load-bearing idea | Listener knows it but hasn't thought about it lately |
| `skip` | **A one-line notation handshake — never silence** | Listener knows it cold |

> **`skip` is not nothing.** Even material you know cold has to have its *notation* fixed before it's used — a real lecturer says "recall we write m for the magnetization" and moves on. Silence breaks the lecture the first time a symbol appears unannounced.

Depth is set three ways, all of which the system needs:

1. **Upfront calibration** — a per-block control before starting, plus presets ("I do quantum info", "just the theorem"). Cheap, no dialogue, and the estimated runtime updates live so the tradeoff is visible.
2. **Mid-lecture skip** — *"I know this, move on."* Jumps past the current block and marks it skipped.
3. **Mid-lecture expansion** — *"wait, explain Davies generators."* Runs the `full` variant of a block that was skipped, then returns. Distinguished from a notation lookup by phrasing: "what is X" gets a one-line answer, "explain X" gets the block.

**The invariant this introduces, and it is easy to get wrong:**

> Anything the core content references — any `point`, `annotate`, or `arrow` target — must be defined at **every** depth of its block.

Discovered the hard way: the core lecture draws an arrow from the magnetization definition to the main result, and at `brief`/`skip` depth that target didn't exist, so the arrow dangled under three of the four presets. The fix is to author the same `id` at all three depths, which is exactly what "skip is a notation handshake" means operationally. **Validate referential integrity under every depth combination, not just the default one.**

### 3.3 Lecture planner — the actual intellectual contribution

**Papers are written in logical order. Lectures are taught in pedagogical order.** Converting between them is the core of this system and the reason it's more than a TTS wrapper.

Concretely, the planner must:

1. **Topologically sort** the concept graph so nothing is used before it's defined.
2. **Reorder pedagogically** — a proof is typically taught as: motivate the difficulty → state the theorem → give the one-line idea → do a toy case → then the general proof. Papers almost never present it that way.
3. **Expand elisions.** "It follows easily," "a routine computation shows," "by standard arguments." A lecture cannot skip these; a blackboard is where they get done. Each expansion is generated *and tagged* as derived, never presented as if it came from the paper.
4. **Budget time.** A 30-page paper is not a 30-minute lecture. Assign each node one of: `full` (proved on the board), `sketch` (idea only), `cited` (stated and moved past), `skipped`. Expose this as a user-facing dial: *"60-minute overview"* vs *"3-hour full proof."*
5. **Choose examples.** Instantiate abstract statements at $n=2$, or on a concrete function, or in the simplest nontrivial case. This is what separates a good lecturer from a text-to-speech reader.

Output: an ordered list of **lecture beats**, each with a target duration, a set of graph nodes, and a teaching intent.

### 3.4 Board choreographer — beats → BIL ops

This is a **layout engine, not an LLM**. The LLM proposes what to write; the choreographer decides where it goes and what gets erased.

Policy:

- Board = **3 panels** (matching a real lecture hall's sliding boards).
- Every item has a persistence class: `pinned` (theorem under discussion, standing notation), `working` (current derivation), `ephemeral` (scratch).
- **Erase rule:** never erase anything referenced by the current beat or the next two beats. When space is needed, evict the least-recently-referenced `working` content. `pinned` items only get evicted at a section boundary, and get re-written if referenced again.
- **Overflow rule:** if a beat cannot fit, either scroll the panel or split the beat. Never overlap.
- **Alignment:** equation chains align on their relation symbol, like a human writing `= ... = ... ≤ ...` down the board.
- **Character staging** *(added after M0)*: the lecturer is a moving occluder, and must never stand in front of what he is writing. Score every standing position along the foot of the board by the content it would cover — pinned material weighted heaviest, the live line heaviest of all — minus a pull toward the active line so he still reads as connected to it. Walk to the best. Opacity duck only as a last resort. This is a per-op layout pass, not a rendering detail.

Run the choreographer as a constraint check *at compile time*, so layout failures surface before the lecture starts, not during it.

### 3.5 Renderer — making it look and feel like chalk

**Do not use Manim for the live path.** Manim's Cairo backend takes seconds-to-minutes per scene; it is a video tool, not a real-time one. Reserve it (or headless-browser capture) for offline export.

Live stack: **KaTeX → SVG → animated `<canvas>`/SVG in the browser.** Renders in milliseconds.

Getting the handwriting feel without a handwriting model:

- Take the glyph outline paths out of the KaTeX/MathJax SVG output; reveal them **sequentially, left to right, at ~8–15 glyphs/sec** via `stroke-dashoffset` or a sweeping mask. Sequential reveal at writing speed is what the eye reads as "being written" — far more than stroke realism.
- Per-glyph jitter: ±1.5° rotation, ±1px baseline offset, slight scale variance. Uniform typesetting is the thing that reads as "machine."
- Chalk texture: grainy alpha mask + slight bloom on a dark green/slate background. Optional dust particles on erase.
- Use a chalk-flavored math font (Chalkduster-alikes, or a lightly roughened Computer Modern).
- Sound design matters more than you'd expect — chalk taps on write, a soft sweep on erase.

**De-risk this first.** See M0 in §7.

### 3.6 Real-time interaction loop

- **Transport:** WebRTC to a native speech-to-speech model (OpenAI `gpt-realtime-2.1` or Gemini Live). Native audio-in/audio-out avoids the STT→LLM→TTS latency stack. Server-side VAD plus `response.cancel` gives you barge-in essentially for free — the lecturer stops mid-sentence when you start talking, exactly like a real one.
- **Presenter tools** (function calls exposed to the realtime model):
  `lecture.pause()`, `lecture.resume()`, `lecture.rewind(beat)`, `lecture.jump_to(node_id)`,
  `board.point(target)`, `board.scratch(latex)`, `board.annotate(...)`, `board.erase_scratch()`,
  `kb.lookup(symbol|node_id)`, `escalate_to_reasoning(question)`.
- **Two-tier routing** — this is how you hit the latency target:

| Tier | Handles | Path | Target |
|---|---|---|---|
| **Reflex** (<300ms) | "what's that symbol", "go back", "say that again", "where did that come from" | Direct KB lookup, no LLM generation | ~200ms |
| **Fast** (<2s) | Questions answerable from the paper + lecture plan | Small model + graph retrieval | ~1.2s |
| **Deep** (5–60s) | Genuine new math: "what if we drop compactness?" | Reasoning model, **visible thinking state** | acknowledge in <500ms, answer when ready |

The critical trick: the reflex tier **always** speaks within 500ms — even if only to say "hm, let me think about that" — then hands off. Perceived latency is governed by time-to-first-audio, not time-to-answer.

### 3.7 The thinking state — turn a liability into a feature

You said it's fine for the character to visibly think. Go further and make it the best part of the system: **stream the reasoning into a scratch corner of the board.**

While the deep tier runs, the avatar turns to the board and writes partial working — trial substitutions, a counterexample attempt, a crossed-out dead end. This is exactly what a real lecturer does when asked something they haven't prepared, it makes 30 seconds of latency feel like insight rather than a spinner, and it's more pedagogically honest than a polished instant answer.

Wire it as: reasoning-token stream → filter for anything that looks like math → `board.scratch()` ops in the margin → `board.erase_scratch()` once the real answer is composed.

### 3.8 Character

Keep it cheap. A 2D vector rig (Rive or Lottie, or a hand-built SVG rig) with states: `idle`, `writing(x,y)`, `pointing(x,y)`, `thinking`, `listening`, `speaking`.

The **pointing hand is the pedagogically important part** — pointing at the right subexpression at the right moment does more for comprehension than any amount of facial realism. Mouth can be amplitude-driven or viseme-driven from TTS timestamps; nobody will look at it. Budget one week, hard cap.

---

## 4. Correctness — the part that matters most for math

A lecturer who confidently writes a false step is worse than useless. Layered defenses:

1. **Syntactic gate.** Every `latex` field is KaTeX-parsed before it can enter a board script. Parse failure → auto-repair loop → hard fail if it doesn't converge. Zero malformed math ever reaches the board.
2. **Provenance on every op.** Each written line is tagged `verbatim` (from the paper, with §/equation ref), `derived` (agent-expanded, with confidence), or `illustrative` (example the agent chose). Render this subtly — e.g. derived steps get a faint margin tick. A user should always be able to ask "is that in the paper?" and get a straight answer.
3. **Symbolic spot-checks.** Where a step is mechanical (expand, factor, differentiate, substitute), verify it with SymPy at compile time. This won't cover analysis or category theory, but it catches a real and common class of algebraic hallucination for free.
4. **Uncertainty is a first-class board op.** "I don't think the paper justifies this — here's my best reconstruction" written in the margin is a *correct* output, not a failure.
5. **Stretch: Lean/mathlib cross-reference.** For steps invoking named standard results, check the statement against mathlib. Genuinely valuable for a math audience; explicitly out of scope for v1.

---

## 5. Prior art — what exists and what's actually open

| System | What it does | Gap it leaves |
|---|---|---|
| **Paper2Video / PaperTalker** (2510.05096) | Multi-agent paper → slide-based presentation video, with talking head, cursor grounding, TTS. Benchmark of 101 paper–video pairs. | **Slides, not blackboard. Non-interactive.** Conference-talk register, not lecture register. |
| **TheoremExplainAgent** (TIGER-Lab) | Agentic long-form theorem explanation via Manim; TheoremExplainBench, 240 theorems. | One theorem, not a paper. Offline video. No interaction. |
| **Code2Video / MMMC** | Planner→Coder→Critic emitting Manim; establishes that *code as intermediate representation beats pixel-space video generation* for educational content. | Validates your architecture. Still offline, still single-concept. |
| **Manimator**, generative-manim, manim-generator | Paper/prompt → Manim, code-writer + reviewer loops. | Render-time only. Common failure: syntax errors, and even valid code often produces incoherent layouts. |
| Commercial AI whiteboard tutors | Real-time conversation over a canvas. | No paper ingestion; no serious math typesetting; no long-form proof exposition. |

**The open ground is exactly your intersection: long-form, board-based, real-time-interruptible, faithful to a specific paper.** Nobody is sitting on that. The literature also independently confirms two of your choices — code/structured-IR beats pixel video generation, and Manim-as-final-renderer is where these systems break down (which is why the BIL sits between the agent and *any* renderer here).

---

## 6. Tech stack

**Frontend** — TypeScript + React; board as `<canvas>` (or SVG for easier hit-testing); KaTeX for typesetting; WebRTC to the realtime model; Web Audio for chalk SFX; Rive/Lottie for the avatar.

**Backend** — Python + FastAPI. Ingestion: `latexpand`, `de-macro`, plasTeX, LaTeXML. Verification: SymPy. Orchestration: a plain state machine — resist agent frameworks here; the control flow is small and you want it debuggable.

**Storage** — Semantic graphs and board scripts as JSON in Postgres (or SQLite to start). Board scripts are your most valuable artifact: version them, they're your regression suite.

**Offline export** — Playwright driving deterministic board-script playback + ffmpeg capture. Simpler and more faithful than re-implementing in Manim.

---

## 6b. What M0 settled — and what it changed

`m0-board-spike.html`: a hand-authored 9-minute lecture on the Banach fixed-point theorem, three boards, 56 ops, no AI anywhere in it. Verdict: **passed** — the board reads as a lecture. Four things came out of it that the original plan had wrong or missing.

**1. Narration is a compiler output, not a TTS preprocessing step.** ← *the important one*

The plan treated LaTeX→speech as a rendering-time utility (§A.2 of the demo doc). Wrong. Real lecturers say what they write *as* they write it — "d of x n plus one, x n… equals… d of T x n, T x n minus one" — with commentary wrapped around the literal reading, and the writing pace *slaved to the speaking pace*. That makes the spoken form a first-class field of every board op, which the **compiler** must emit and be evaluated on. Hence BIL v0.2 (§2).

Consequence: a chunk must be independently well-formed LaTeX, because chunk-level glyph counts are what hold speech and handwriting in sync. That's a hard constraint on the compiler's output, and it is cheaply checkable — 26/26 write ops in the spike verified to align exactly.

**2. The lecturer is an occluder and must be staged.** Standing him in one place and carving out padding lets the character constrain the mathematics. He has to walk. Now a scoring pass in the choreographer (§3.4); replayed against all 31 write ops, worst overlap with the live line is 0 px².

**3. The reflex and fast tiers really do need no model.** The spike's Q&A routes through a 10-entry notation table and 13 facts standing in for the semantic graph — and answers most natural questions in single-digit milliseconds with zero inference. This was an assertion in the plan; it is now evidence. It also means **the notation table is the highest-value artifact the compiler produces**, not a side output.

**4. Validation-by-construction works and should become the regression harness.** Already running, all from the board script without rendering a frame: LaTeX compiles under `throwOnError`, chunk↔glyph alignment, referential integrity (no reference-before-write, nothing erased while still referenced), KB reference resolution, and a 26-case question-routing test. Keep every one of these and run them against *generated* scripts from M1 onward.

**What M0 did not settle:** anything about the compiler — every word of that lecture is hand-written. And voice: browser TTS has an audible ceiling, and pre-rendering with a real engine is still the fix.

---

## 6c. The target paper

**[arXiv:2607.21798](https://arxiv.org/abs/2607.21798) — *Spectral Gap of the Davies Generator for the Mean-Field Heisenberg Model***
Basso, Bergamaschi, Lin, Ragone, Stubbs · 23 July 2026 · quant-ph + math-ph · **63 pages, 1 figure**

Main result: for the mean-field Heisenberg ferromagnet, the Davies generator's spectral gap is Θ(1) for β<2 and Θ(n⁻¹) for β>2, with the low-temperature slowdown witnessed by the total magnetization order parameter. Two technical engines: a comparison argument with auxiliary generators bounding dissipation on nontrivial SU(2) and Sₙ representations, and a decomposition of observables into spherical tensor operators that exposes a monotonicity.

This is a good choice and a hard one. Five consequences for the build:

| Property | What it forces |
|---|---|
| **63 pages** | Time budgeting (`full`/`sketch`/`cited`/`skipped`) is required in M1, not a later refinement. This is a 3–4 lecture series or one 90-minute overview, never a single sitting. |
| **Heavy presupposed background** — Davies generators, Lindbladians, Gibbs states, spherical tensor operators, Schur–Weyl | The semantic graph needs a **prerequisite layer**: concepts the paper *uses but never defines*. The original plan only modelled what's inside the paper. For a frontier paper that's not enough, and it's where a lecture earns its keep over the PDF. |
| **Operator-algebraic and representation-theoretic** | **SymPy verification is close to useless here.** Defense 3 in §4 largely doesn't apply. Correctness has to lean on provenance tagging, explicit uncertainty, and human review. Plan accordingly — do not assume the symbolic checker is covering you. |
| **1 figure** | Almost entirely symbolic, which suits a blackboard. Boards are bad at figures; this paper barely needs any. |
| **Lin Lin is at Berkeley** | **Author-in-the-loop evaluation is available.** This is the single strongest faithfulness signal obtainable and nothing else on the eval list comes close. Use it. |

**Scoping caution.** Do not point the first compiler run at all 63 pages. Pick one self-contained slice and compile that. Same paper, same difficulty class, one-tenth the surface area. Widen only once the slice is good.

**Slice chosen: §3.5 + §3.7 — "the gap is Θ(n⁻¹) for β > 2", both directions.** `m1-slice-lecture.html`. It is the best-shaped teachable unit in the paper:

- **Lower bound (Thm 3.11)** is three lines of operator inequality on top of a Casimir computation. Introduce the SU(2) group mixer `L_su(2)` — a scalar multiple of the quadratic Casimir, so representation theory hands you `gap = 1` for free — then observe `L_loc = (1/n)L_su(2) + L_{B}` with `−L_B ⪰ 0`, so `0 ⪯ −(1/n)L_su(2) ⪯ −L_loc`. The factor of n⁻¹ is not bookkeeping: the mixer's jumps are the *total* spin operators, of norm Θ(n).
- **Upper bound (Thm 3.21)** is a single Rayleigh quotient on the order parameter `S_tot^Z`. `E ≤ n`, `Var ≥ c·c_β²·n²` with `c_β = ½ − 1/β` — and the phase transition falls straight out of that constant being positive exactly when β > 2.
- They meet. Tight, self-contained, and the pedagogy writes itself: pure symmetry gives the lower bound with no temperature anywhere; the physics enters only through the test observable.

**Deliberately excluded and stated aloud in the lecture:** the ℓ = 0 sector (§3.4, birth–death chain, Cheeger + Laplace) and the high-temperature side (§3.6, spherical-tensor monotonicity). Those are separate sessions.

**A finding worth recording.** Eq (3.30) as printed reads `L_loc|_{A^(ℓ)} ≥ Ω(n⁻¹)·1`. Since `L_loc ⪯ 0` that cannot be meant literally, and the parallel statement Eq (3.18) does carry the minus sign. The board uses `−L_loc`. Probable typo — **ask Lin Lin.** This is exactly the class of thing author-in-the-loop review is for, and it argues for making sign/direction consistency an explicit compiler check.

### 6d. Lecture shape: three acts *(the current build)*

`m1-slice-lecture.html` now covers the whole paper, in the structure a real seminar uses:

| Act | Content | Full depth |
|---|---|---|
| **I — Background** | Five prerequisite blocks, each at `full`/`brief`/`skip` | 16 min (1 min if skipped) |
| **II — The paper** | Problem, why it was open, why this model, main theorem, proof strategy sector by sector, the two reusable techniques, what's new | 21 min |
| **III — Deep dives** | Three results proved properly on the board, individually selectable | 26 min |

**~1h04 of scripted delivery at full depth**, landing in the 1.5–2h range once questions are included — which is the point of the format, not an accident of it.

Act II is where "teach the whole paper" actually happens: all four bounds, both key techniques, the algorithmic corollary, and the classical lineage, at the level of ideas. Act III then proves three things in full:

1. **Where β = 2 comes from.** Expand the free energy `f_β(x) = −(β/4)x² − H_b((1+x)/2)` about zero: the quadratic coefficient is `(2−β)/4`. The critical point is exactly where it vanishes. A Landau transition derived live, and it also explains the `O(n^{-1/2})` at criticality — Laplace's method needs `f'' ≠ 0`, and it degenerates precisely there.
2. **The SU(2) mixer lower bound** (§3.5).
3. **The order-parameter upper bound** (§3.7).

That set is deliberate: the conceptual origin of the critical point, plus both halves of a tight result that meet at Θ(n⁻¹).

**Design note carried forward.** Prerequisites are a shared library (`PREREQ`), not duplicated per session; a lecture declares which blocks it uses and the plan builder prepends them at the chosen depth. That is how the real compiler should emit them too — course-level, injected per lecture.

---

## 7. Milestones

Sequenced by **uncertainty, not by pipeline order.** This is the main revision after M0.

The original plan ran ingestion → compiler → real-time, because that's the order data flows. That's now the wrong order. LaTeX parsing is tedious but *known* engineering; the compiler is the part that decides whether the project works at all. And the compiler can be tested with no ingestion pipeline whatsoever — by hand-authoring the semantic graph, exactly as M0 hand-authored the board script. So it moves to the front, and ingestion drops to M3.

### ~~M0 — Board feel spike~~ ✅ **done, passed** (see §6b)
BIL v0.2 schema + validator + renderer + hand-authored Banach lecture + live three-tier Q&A. `m0-board-spike.html`.

### M1 — The compiler, on a hand-built graph (weeks 1–3) ← **you are here**

Hand-author the semantic graph for **one slice** of arXiv:2607.21798 (§6c) — nodes, edges, notation table, prerequisite layer. Then have a frontier model compile it into a board script, and play it in the existing renderer.

The graph is written by you; only the *lecture* is generated. That isolates the question.

> **Gate — the real one:** is the generated lecture as good as the Banach one you wrote by hand? Watch both. If a frontier model given a clean, complete graph cannot produce a decent board script, no amount of ingestion work rescues the project, and you'll know inside three weeks.

Deliverables: graph schema; hand-built graph for one slice; compiler prompt + BIL-constrained decoding; generated script passing the full M0 validation suite; side-by-side viewing.

Watch specifically for the four failure modes worth naming now: narration that reads symbols aloud without *teaching* them; elisions expanded wrongly; board layout that technically validates but is unreadable; and time budgeting that tries to do all 63 pages.

### M2 — Correctness and the prerequisite layer (weeks 4–5)

The compiler's first drafts will contain errors, and §4's SymPy defense barely applies to this paper (§6c). So this milestone is about the defenses that *do* work: provenance tagging on every line, explicit uncertainty as a board op, and a critic pass by a **different model family** than the compiler.

Also build the prerequisite layer — the concepts the paper presupposes and never defines. For a 63-page quant-ph paper this is most of what makes a lecture better than the PDF.

> **Gate:** hand the generated lecture to one of the authors. Ask them to mark every derived step correct / wrong / unjustified. **Wrong steps are the number that matters** — target zero, and treat any nonzero count as blocking.

### M3 — Ingestion (weeks 6–7)

Now automate what you hand-built in M1. arXiv `e-print` → `latexpand` → `de-macro` → plasTeX/LaTeXML → typed graph + notation table.

> **Gate:** the auto-extracted graph for arXiv:2607.21798 matches your hand-built one on the slice you already did. That's a real diff, not a vibe — which is precisely why M1 comes first.

### M4 — Real-time loop for real (weeks 8–10)

Replace the spike's mock router with the actual thing: streaming voice, true barge-in, tool calls, three-tier routing over the *generated* graph rather than a hand-written KB.

> **Gate:** interrupt a generated lecture with "wait, why does that follow?" and get a correct on-board answer in under 2 seconds, then resume cleanly.

### M5 — Voice, polish, export (weeks 11–12)

Pre-rendered or streaming TTS to replace browser speech — the demo's weakest link. Character polish, sound, video export for people who won't sit through a live session.

> **Gate:** three lectures from arXiv:2607.21798, each watched end-to-end by someone who hasn't read the paper. Ask them what they learned.

---

## 8. Evaluation

Lightweight but real — enough to catch regressions, not a benchmark paper.

**Automatic, from the board script alone (no rendering needed).** All of these are already implemented in the M0 spike — carry them forward and run them against *generated* scripts:

- LaTeX validity rate under `throwOnError` (target: 100%).
- **Chunk↔glyph alignment** — every `{tex, say}` chunk's glyph count sums exactly to the joined render. Misalignment means speech desyncs from handwriting. *(new in v0.2)*
- **Referential integrity:** was anything erased while still referenced? (Pure graph check — surprisingly strong signal for board quality.)
- **Character occlusion:** worst overlap between the staged lecturer and the live line. Target 0 px². *(new)*
- **Overlap/overflow violations:** zero.
- **Narration coverage:** zero write-chunks with no spoken form.
- **Referential integrity under every depth combination** — not just the default. Adaptive prerequisites make it possible for core content to point at something the listener's settings filtered away. *(new at M1)*
- **Cross-block reference invariant:** any id referenced from outside its block is defined at all three depths. *(new at M1)*
- **Depth coverage:** every prerequisite block defines `full`, `brief` and `skip` variants.
- **Term-before-symbol lint** *(implemented — `verify/check_lecture.mjs`)*: no technical term ("Lindbladian", "inverse temperature") spoken in a `full`-depth segment before its defining equation is written. Caught by a human at M1 — the narration said "Lindbladian" for a minute while the board never showed the GKSL form. A compiler will make this mistake constantly; the lint maps each term to the board id defining it and allows a 4-op grace window, since “we want a Lindbladian — here it is:” is correct teaching. Beyond that window, or never written at all, is a failure.
- Coverage: fraction of the paper's theorems/lemmas at `full` or `sketch`.
- Derived-step ratio and mean confidence.
- ~~SymPy check pass rate~~ — **largely inapplicable to the target paper** (§6c). Keep the harness for future algebraic papers; do not count on it here.

**Runtime:**

- Time-to-first-audio after user speech ends: p50 / p95.
- Barge-in cut-off latency.
- Resume correctness after interruption.

**Human (n small, but do it):**

- **Author-in-the-loop faithfulness.** An author of arXiv:2607.21798 marks each derived step correct / wrong / unjustified. **Wrong steps are the metric that matters** — target zero. This is available to you (§6c) and is worth more than every automatic metric combined.
- "Would a first-year grad student learn this from this lecture?" — 1–5.
- Side-by-side vs. just reading the paper for 30 minutes. Given the "five hours to absorb one paper" premise, this is the metric that tests the actual thesis.

Build a fixed regression set as you go: the hand-written Banach script from M0 is the quality bar, and each generated script that passes review joins the suite.

---

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| ~~Board looks fake/uncanny~~ | — | **Retired.** M0 passed. |
| Agent writes false math confidently | **High** | Provenance tags, explicit uncertainty ops, cross-family critic, author review. ⚠️ **SymPy checking does not cover the target paper** (§6c) — this risk is materially higher than the original plan assumed. |
| **Compiler produces valid-but-lifeless lectures** | **High** | The new top risk. A script can pass every automatic check and still be a symbol-reader rather than a teacher. Only defense is the M1 side-by-side gate against the hand-written Banach lecture. |
| 63-page paper doesn't fit any sensible lecture | **High** | Compile one self-contained slice first (§6c). Time budgeting is an M1 requirement, not a later refinement. |
| Latency blows past 2s | Medium | Speech never blocks on board rendering. Reflex tier always answers <500ms. Native speech-to-speech, not a chained pipeline. |
| Interruption corrupts lecture state | Medium | Board script is immutable; interruptions are a *splice layer* on top. Resume = pop the splice. |
| Long papers → incoherent lectures | Medium | Time budgeting with `full`/`sketch`/`cited`/`skipped`; user-facing duration dial. |
| Avatar scope creep eats the project | Medium | Hard one-week cap. 2D only. Revisit only after M4. |
| Domain breadth (analysis vs. algebraic geometry vs. combinatorics) | Medium | **Pick one genre for v1.** Suggest: papers with concrete computable content (analysis, numerics, probability) where SymPy checking and worked examples actually help. |
| Cost per lecture | Low | Compilation is one-time per paper and cacheable. Only the live loop is per-session. |

---

## 10. Explicitly out of scope for v1

Photorealistic talking head · video-generation models · real stroke-level handwriting synthesis · multi-paper synthesis · non-math domains · Lean/mathlib formal verification · multi-user classroom sessions · mobile.

---

## 11. Open research questions (if you want a paper out of this)

The framing is not "we made an AI lecturer." It's one of these:

1. **Logical order → pedagogical order.** Is the paper→lecture reordering learnable, and does it measurably improve comprehension over presentation in source order? This is the cleanest, most defensible contribution.
2. **Board-space management as a planning problem.** What's the right formalism for "what stays visible"? It's a scheduling problem with a real objective (comprehension) and it's never been studied.
3. **Elision expansion.** Can a model reliably detect *and correctly fill* "it follows easily"? Measurable, useful beyond this system, and a nice standalone benchmark on arXiv math.
4. **Visible reasoning as pedagogy.** Does streaming a model's thinking as scratch work improve learning outcomes vs. showing only the polished answer? Cheap human study, genuinely novel.

---

## 12. What to build tomorrow

M0's list is done. The new one:

1. **Pick the slice.** Read arXiv:2607.21798 and choose one self-contained result — the high-temperature Θ(1) bound is the obvious candidate. Write down where it starts and stops.
2. **Define the graph schema.** Node types, edge types, notation table, prerequisite layer. Pydantic, exports JSON Schema, same discipline as BIL.
3. **Hand-build the graph for that slice.** This is the day's real work, and it doubles as the ground truth M3 will be diffed against.
4. **Write the compiler prompt.** Graph in, BIL v0.2 out, grammar-constrained so the output is always valid. Emphasise the `{tex, say}` chunking — that's the part a model will get lazily wrong.
5. **Compile it, run the M0 validation suite on the output, and play it in the existing renderer.**
6. **Watch it back-to-back with the Banach lecture.** That comparison is the M1 gate.

Step 6 is the whole milestone. Steps 1–5 exist to make it possible.
