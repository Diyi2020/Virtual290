# Virtual290

An AI lecturer that teaches a mathematics paper on a blackboard — writing and narrating in sync, chalk-style, and interruptible by voice: ask a question mid-proof and it stops, answers, and picks up where it left off.

**Status: research prototype.** The board renderer, adaptive lectures, and live Q&A work today; the lectures themselves are still hand-authored. The compiler that generates them from a paper is the next milestone (see [`PLAN.md`](PLAN.md)).

## Demos

| File | What it is |
|---|---|
| [`m0-board-spike.html`](m0-board-spike.html) | Banach fixed-point theorem, ~9 min. The original board-feel spike. |
| [`m1-slice-lecture.html`](m1-slice-lecture.html) | [arXiv:2607.21798](https://arxiv.org/abs/2607.21798) (spectral gap of the Davies generator for mean-field Heisenberg), ~1 h. Three acts: adaptive prerequisites → the paper's ideas → three proofs in full. |

## Run it

```bash
git clone <this repo> && cd Virtual290
python3 -m http.server 8731
# open http://localhost:8731/m1-slice-lecture.html
```

Or double-click `start-mac.command` / `start-windows.bat`. No build step, no API key, no internet — KaTeX is vendored in `assets/`. Serving over localhost (rather than opening the file directly) is only needed for microphone access in Chrome/Edge.

Any laptop from the last ~6 years works. Best voices: **Edge on Windows** (Microsoft Natural voices, no install) or **Safari/Chrome on macOS** after installing a Premium voice — System Settings → Accessibility → Spoken Content → Manage Voices, though the menu location varies by macOS version (search "spoken" in System Settings if you don't see it). After installing a voice, click **⟳** next to the voice menu — it rescans and reports what it found. If the voice still isn't listed: **fully quit the browser (Cmd-Q, not just the window) and reopen** — voices are scanned once at launch. Verify the install itself with `say -v Ava hello` in Terminal; if Terminal speaks but the browser doesn't list her, try Safari — some browsers never expose newly installed system voices, and Siri voices never appear to web pages at all. Headphones recommended if you enable always-on listening — otherwise the lecturer hears himself and interrupts his own sentence.

Long formulas cramped? Switch to **2 boards** or **1 big board** in the toolbar (best chosen before pressing Play).

## What to try

Before playing the long lecture, tell it what you already know (per-topic: *teach it / remind me / I know it*) and which proofs to do in full. Then, at any point, by voice (hold **Q**) or text:

- *"What is a Davies generator?"* — notation lookup, answers in milliseconds, points at the definition
- *"Where does the factor of 1/n come from?"* — retrieves the argument, points at the right line
- *"Explain Schur–Weyl"* — re-teaches a prerequisite you skipped, then returns
- *"Slow down"* / *"go back"* / *"I know this, move on"*

Questions outside its knowledge base escalate to a visible thinking state — and it says "I don't know" rather than guessing. If [Ollama](https://ollama.com) is running locally it's auto-detected and answers those instead.

## How it works

```
paper ──(offline compiler: expensive, careful)──▶ board script ──(online presenter: fast, interruptible)──▶ lecture
```

The board script is a typed op stream (`write`, `annotate`, `point`, `erase`, …) where every written chunk carries both LaTeX and its spoken form, revealed glyph-by-glyph in sync with speech. Scripts are validated before playback: LaTeX compilation, speech–handwriting alignment, referential integrity under every prerequisite-depth combination, and a provenance tag on every line (verbatim from the paper vs. reconstructed — reconstructed lines get a visible margin tick).

`verify/check_lecture.mjs` runs eight checks against a script without rendering it — LaTeX, speech/handwriting alignment, referential integrity under every prerequisite-depth combination, and a *term-before-symbol* lint that fails if a technical term is spoken more than a few ops before its defining equation reaches the board. `cd verify && npm install && npm run check`.

`compiler/` holds the model layer for the generation milestone: providers are configured by role in YAML, keys stay in your environment, and a cross-family critic pass (e.g. Anthropic compiles, OpenAI reviews) is enforced at load time — a model reviewing its own output shares the blind spots that produced the error.

## Repo map

```
m0-board-spike.html      demo 1 — Banach, single file
m1-slice-lecture.html    demo 2 — full paper lecture, single file
assets/katex/            vendored KaTeX (offline math rendering)
compiler/                provider layer + cross-family critic (Python)
verify/                  board-script checks — run before playing any lecture
PLAN.md                  architecture & milestones — start here
DEMO_AND_MODEL_STACK.md  hardware/software requirements, model options
```

## Caveats

Hand-authored content was verified line-by-line against the paper's source, but this is a prototype: browser TTS quality varies by platform, voice input needs Chrome/Edge/Safari, and nothing here has been reviewed by the paper's authors yet. One suspected typo in the paper (a sign in Eq. 3.30) is flagged in `PLAN.md` §6c.
