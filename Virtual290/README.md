# Virtual290 — Board Spike

A prototype of an AI that lectures a mathematics paper on a blackboard, in real time, and lets you interrupt it with questions.

This is an early spike, not a product. It exists to answer one question — *does a programmatically-drawn chalkboard actually feel like a graduate lecture?* — before any AI gets built. The lecture (the Banach fixed-point theorem, about 9 minutes) is hand-authored. **Nothing here calls a language model unless you deliberately point it at one.**

---

## Quick start

1. **Extract the folder** if it arrived as a `.zip`. Don't run it from inside the zip preview.
2. **Double-click the launcher** for your machine:
   - macOS / Linux → `start-mac.command`
   - Windows → `start-windows.bat`
3. A browser opens. Press **Play**.

That's it. No install, no sign-in, no API key, no internet.

> **First-run security prompts are normal**, because the folder came from another computer.
> **macOS:** right-click `start-mac.command` → **Open** → **Open**. Once only.
> **Windows:** SmartScreen → **More info** → **Run anyway**.

**Don't want to run a launcher?** Just double-click `m0-board-spike.html`. Everything works except the microphone in Chrome and Edge — type your questions instead. (In Safari the mic usually works even this way.)

---

## Supported environments

Any laptop or desktop from roughly the last six years. **Phones and tablets are not supported** — the layout assumes a wide screen.

| OS + browser | Board | Voice out | Ask by voice | |
|---|---|---|---|---|
| **Windows + Edge** | yes | **best available** | yes | ← best on Windows |
| Windows + Chrome | yes | robotic | yes | |
| Windows + Firefox | yes | robotic | no — type | |
| **macOS + Safari** | yes | very good | yes | ← simplest path |
| macOS + Chrome / Edge | yes | very good | yes | |
| macOS + Firefox | yes | very good | no — type | |
| Linux + Chrome / Edge | yes | poor | yes | needs `espeak-ng` |
| Linux + Firefox | yes | poor | no — type | |

"Ask by voice" needs the launcher on every browser except Safari, because Chrome, Edge and Firefox block microphone access for files opened directly.

**Verification status, honestly:** macOS + Safari is confirmed working. Every other row is derived from documented browser behaviour but has not been run end to end. If something misbehaves, the page prints a diagnostic line at the bottom telling you what it found — please send that line back.

### What you need

- A laptop. **No GPU.** The whole thing is 900 KB.
- A browser from the list above.
- Speakers or, better, **headphones**.

### What you don't need

- Internet — KaTeX and its fonts are bundled in `assets/`. Keep that folder next to the HTML.
- An API key, an account, or any install.
- Python, Node, or any developer tooling. The Windows launcher falls back to PowerShell, which every Windows machine already has.

---

## How to use it

**Play / Pause** — the button, or the **spacebar**.

**Ask a question** — three ways:

| | How |
|---|---|
| Type | Click the text box, type, press **Enter**. Always works. |
| Push to talk | Hold the **🎤** button, or hold the **Q** key. Speak. Release. |
| Always listening | Tick the box. He'll stop mid-word the moment you speak. **Headphones required.** |

Interrupting is meant to be rude — he stops mid-sentence, answers, then picks up exactly where he left off, including finishing a half-written line.

**Other controls:** playback speed, a **chalk** toggle (turn it off to see how much the texture is doing), and a voice picker where ★ marks a good voice.

> **Why headphones matter.** With "always listening" on and open speakers, the microphone hears the lecturer's own voice, decides someone is talking, and he interrupts himself in a loop. Headphones make this vanish. Push-to-talk is fine on speakers.

### Things worth asking

| Ask | What happens |
|---|---|
| *"What is q?"* | Looks it up, points at the definition. A few milliseconds. |
| *"Why is that Cauchy?"* | Retrieves the justification, points at the relevant bound. |
| *"What if q equals one?"* | Writes a counterexample as scratch work, then wipes it. |
| *"Say that again"* · *"go back"* · *"slow down"* · *"keep going"* | Control commands. |
| *"Can you relate this to the implicit function theorem?"* | Thinks visibly — then **admits it doesn't know.** |

That last one is deliberate. Questions are routed through three tiers, and the badge shows which one answered plus its real measured latency. The first two tiers use **no language model at all** — they retrieve from a small hand-written knowledge base standing in for the structure a real system would extract from the paper. When a question falls outside it, saying so beats inventing a plausible wrong answer. For mathematics that's the only acceptable default.

**Optional — a real third tier.** If you have [Ollama](https://ollama.com) running locally, the page detects it on load and sends unmatched questions to your local model. No key, no configuration. You may need to start it as `OLLAMA_ORIGINS='*' ollama serve` so the browser can reach it.

---

## Getting a decent voice

Speech quality depends entirely on what your browser exposes, and the defaults are rough. The dropdown ranks them automatically; ★ means a good one.

- **Windows — open it in Edge.** Edge exposes Microsoft's *Natural* neural voices (Aria, Guy, Jenny, Ryan). They're the best-sounding option on any platform and need no install. Chrome on the same machine gets the old robotic voices. This is the single biggest difference between any two setups here.
- **macOS** — System Settings → Accessibility → Spoken Content → System Voice → **Manage Voices** → install **Ava** or **Zoe (Premium)**. A minute of work, large improvement.
- **Linux** — `sudo apt install espeak-ng`, and lower your expectations.

Browser speech still has a ceiling you will hear. Pre-rendering the narration with a proper text-to-speech engine is the real fix and isn't done yet.

---

## Privacy — what leaves your machine

Almost nothing, but not quite nothing, and the exceptions are worth knowing before you demo this on unpublished work.

**Stays local:** the lecture, the board, all mathematics, the knowledge base, every question the first two tiers answer, and any Ollama model you connect. No analytics, no telemetry, no tracking.

**Leaves your machine, if you use these features:**

- **Voice questions.** Browser speech recognition is a cloud service. Chrome and Edge send your recorded audio to Google; Safari sends it to Apple. Type instead if that matters.
- **Windows Natural voices in Edge.** These are cloud voices — the narration text is sent to Microsoft. The non-★ local voices stay on the machine.
- **The CDN fallback.** Only if `assets/` is missing. With the folder intact, no request is made.

---

## If something goes wrong

| Symptom | Cause |
|---|---|
| Formulas look like plain letters | `assets/` folder is missing or was separated from the HTML. |
| Mic button does nothing | Opened as a file in Chrome/Edge. Use the launcher. |
| He interrupts himself constantly | "Always listening" without headphones. |
| Voice sounds robotic | See the voice section above. On Windows, switch to Edge. |
| Launcher window flashes and closes | No Python or Node, and PowerShell was blocked. Double-click the HTML instead and type your questions. |
| Nothing happens on Play | Check the diagnostic line at the bottom of the page. |

---

## What this is and isn't

Three things are being tested here, and they're what to pay attention to:

1. **Does the chalk read as handwriting?** Characters appear one at a time with per-glyph jitter and a left-to-right wipe.
2. **Does the narration sound like a professor?** He says what he writes *as* he writes it — "d of x n plus one, x n… equals… d of T x n, T x n minus one" — with commentary wrapped around the literal reading. Writing pace follows speaking pace.
3. **Does interruption feel natural?** Barge-in, answer, resume mid-line.

It is **not** yet: reading real papers, generating its own lectures, or reasoning about mathematics. Those are the next milestones. `PLAN.md` describes the system this becomes.

---

## Files

```
m0-board-spike.html        the demo — one file, no build step
assets/katex/              bundled maths fonts, so it runs offline
start-mac.command          double-click launcher (macOS / Linux)
start-windows.bat          double-click launcher (Windows)
serve.ps1                  PowerShell fallback server, used by the .bat
PLAN.md                    architecture and 12-week build plan
DEMO_AND_MODEL_STACK.md    hardware/software requirements, pluggable model layer
```

Feedback that helps most: did the board feel like a lecture, did the voice pacing work, and did interrupting it feel natural or awkward?
