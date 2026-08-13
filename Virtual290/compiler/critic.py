"""
Virtual290 — cross-family critic pass.

Reviews a generated board script for mathematical faithfulness, using a model
from a DIFFERENT lab than the one that wrote it. Registry refuses to start if
that constraint is violated: a model reviewing its own output reproduces its own
blind spots, which is close to worthless as a check.

The critic never edits. It emits findings, each pinned to a board-op id, and the
build fails on any WRONG. Only a human — ideally an author of the paper — is
allowed to clear those.

    python critic.py board_script.json paper.txt
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict

from providers import registry

VERDICTS = ("WRONG", "UNJUSTIFIED", "IMPRECISE", "OK")

FINDING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["op_id", "verdict", "issue", "confidence"],
                "properties": {
                    "op_id":      {"type": "string"},
                    "verdict":    {"type": "string", "enum": list(VERDICTS)},
                    "issue":      {"type": "string"},
                    "suggestion": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        }
    },
}

SYSTEM = """You are reviewing a blackboard lecture script generated from a mathematics paper.
You did not write it. Your job is to find errors, not to praise it.

For every board line, decide:
  WRONG        the mathematics is incorrect, or misstates the paper
  UNJUSTIFIED  presented as following from the paper but the paper does not support it
  IMPRECISE    technically defensible but sloppy or misleading as taught
  OK           faithful

Pay particular attention to:
  - sign errors and direction of inequalities
  - quantifier scope, and hypotheses silently dropped
  - asymptotic notation: Omega vs O vs Theta, and in which variable
  - normalisation conventions that differ from the source
  - steps tagged 'verbatim' that are in fact the lecturer's reconstruction

Report only real problems. An empty findings list is a valid and useful answer.
Do not soften a WRONG into an IMPRECISE to be agreeable."""


@dataclass
class Finding:
    op_id: str
    verdict: str
    issue: str
    confidence: float
    suggestion: str = ""


def review(board_script: list[dict], source_text: str) -> list[Finding]:
    critic = registry.get("critic")
    compiler = registry.get("compiler")
    print(f"  compiler was : {compiler.name}/{compiler.model}  [{compiler.family}]")
    print(f"  critic is    : {critic.name}/{critic.model}  [{critic.family}]")

    lines = [
        {
            "op_id": op.get("id", f"op{i}"),
            "latex": " ".join(c["tex"] for c in op.get("chunks", [])),
            "spoken": " ".join(c["say"] for c in op.get("chunks", [])),
            "said_around": " ".join(filter(None, [op.get("pre"), op.get("post")])),
            "provenance": op.get("provenance", {"kind": "untagged"}),
        }
        for i, op in enumerate(board_script)
        if op.get("chunks")
    ]

    msg = [{
        "role": "user",
        "content": (
            f"{SYSTEM}\n\n=== SOURCE PAPER ===\n{source_text}\n\n"
            f"=== BOARD SCRIPT ===\n{json.dumps(lines, indent=1)}"
        ),
    }]
    out = critic.complete(msg, schema=FINDING_SCHEMA, max_tokens=16000)
    return [Finding(**f) for f in out.json()["findings"]]


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    board = json.load(open(sys.argv[1]))
    source = open(sys.argv[2]).read()

    print(registry.describe(), "\n")
    findings = review(board, source)

    order = {v: i for i, v in enumerate(VERDICTS)}
    findings.sort(key=lambda f: (order[f.verdict], -f.confidence))

    counts = {v: sum(f.verdict == v for f in findings) for v in VERDICTS}
    print(f"\n{len(findings)} findings: " +
          "  ".join(f"{v} {counts[v]}" for v in VERDICTS if counts[v]))
    for f in findings:
        if f.verdict == "OK":
            continue
        print(f"\n  [{f.verdict}] {f.op_id}  (confidence {f.confidence:.2f})")
        print(f"      {f.issue}")
        if f.suggestion:
            print(f"      -> {f.suggestion}")

    json.dump([asdict(f) for f in findings], open("critic_findings.json", "w"), indent=1)

    if counts["WRONG"]:
        print(f"\nFAILED: {counts['WRONG']} line(s) marked WRONG. "
              f"A human must clear these before the lecture can be played.")
        return 1
    print("\nNo WRONG findings. Still worth an author's eyes before you show anyone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
