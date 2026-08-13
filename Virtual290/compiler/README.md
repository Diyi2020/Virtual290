# Model layer

Code refers to **roles** — `compiler`, `critic`, `narrator`, `fast`, `deep` — never to model names. Swapping models is an edit to `models.yaml`; no code changes.

```
models.yaml     role -> provider mapping, three profiles, verification gates
providers.py    Anthropic / OpenAI / OpenAI-compatible / Ollama behind one interface
critic.py       cross-family review pass; fails the build on any WRONG finding
```

```bash
pip install pyyaml anthropic openai
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
python providers.py                          # print the active profile
python critic.py board_script.json paper.txt # review a generated lecture
```

---

## About connecting ChatGPT

You asked about logging into your OpenAI account so the lecturer could query ChatGPT. Three things make that the wrong path, and one makes a better one available.

**A ChatGPT Pro subscription is not API access.** They're separate products, billed separately. A Pro plan grants no API credits, so the subscription you already have cannot be pointed at this compiler. To use OpenAI models here you create a key at `platform.openai.com`, billed independently of Pro.

**Driving the ChatGPT web interface programmatically breaches OpenAI's terms of service.** Their usage policies prohibit automated or scripted access outside the API. Beyond the legal problem it would be brittle — a UI change breaks it silently, mid-lecture, in front of an audience.

**Credential handling stays with you.** Nothing in this repo asks for, stores, logs, or transmits a key anywhere except to the provider it belongs to. Keys live in environment variables you set yourself, named in `models.yaml`.

**What you actually wanted is better served by the provider layer.** The goal — bring a second lab's model into the pipeline — is architecturally correct and now implemented. It's the `critic` role.

---

## Why the critic must be a different lab

`Registry` refuses to start if the critic and compiler come from the same family:

```
ConfigError: profile 'hybrid': critic and compiler are both 'anthropic' models.
Self-review reproduces the reviewer's own blind spots. Point the critic at a
different family.
```

This isn't fussiness. A model reviewing its own output shares every prior that produced the error, so it agrees with itself. Cross-family review is one of the few cheap, real defences available — and for this project it matters more than usual, because the target paper is operator-algebraic and representation-theoretic, where SymPy verification barely applies (see `PLAN.md` §6c).

So `compiler: anthropic` pairs with `critic: openai`, or the reverse. That is the concrete, useful version of "have ChatGPT in the loop."

## Where a local model fits

The `fast` role — live Q&A that misses the notation table — runs on 2–4k tokens of context and never sees the paper. That's what makes an 8B local model viable there, and it's where per-minute cost accumulates. Compilation is one-time and cacheable; keep it remote until you have evidence a local model compiles good lectures.

For local structured output, set `structured_output: grammar`. The BIL schema is compiled to a decoding grammar (XGrammar under vLLM, GBNF under llama.cpp), which changes the failure mode of a weak model from *corrupt board* to *valid but mediocre board op*. Different risk class entirely.

## Verification gates

`models.yaml` lists eight checks every generated script must clear before it can be played. All eight are implemented and currently pass on the hand-authored lecture, which is what makes them usable as a regression bar for generated ones.

The one worth singling out: **referential integrity is checked under every prerequisite-depth combination**, not just the default. Adaptive prerequisites make it possible for core content to point at something the listener's settings filtered away — that bug appeared in three of four presets the first time it was built.
