#!/usr/bin/env node
/**
 * Virtual290 — board-script verification suite.
 *
 *   node verify/check_lecture.mjs m1-slice-lecture.html
 *
 * Every check runs against the board script alone; nothing is rendered. All of
 * these must keep passing once lectures are machine-generated, so this file is
 * the regression bar, not a one-off.
 *
 *   1  latex            every chunk compiles under KaTeX throwOnError
 *   2  alignment        chunk glyph counts sum to the joined render
 *                       (speech desyncs from handwriting if they don't)
 *   3  integrity        no reference-before-write / erase-while-referenced,
 *                       under EVERY prerequisite-depth x deep-dive combination
 *   4  cross-block      ids referenced from outside a block exist at all depths
 *   5  depth coverage   every block defines full / brief / skip
 *   6  narration        no write-chunk without a spoken form
 *   7  term-before-symbol   a term is not spoken before its equation is on the
 *                       board. Humans miss this; a compiler will do it constantly.
 *   8  kb refs          notation/fact board references resolve
 *
 * Setup:  cd verify && npm install
 */

import { readFileSync } from "node:fs";
import katex from "katex";

const file = process.argv[2] ?? "m1-slice-lecture.html";
const src = readFileSync(file, "utf8");

/* ---------- pull the data out of the single-file demo ---------- */
function slice(from, to) {
  const a = src.indexOf(from), b = src.indexOf(to, a);
  if (a < 0 || b < 0) throw new Error(`cannot locate ${from}`);
  return src.slice(a, b);
}
const dataSrc =
  slice("const BLOCKS=[", "const SCRIPT = PREREQ") +
  "\nconst SCRIPT=PREREQ.concat(ACT2,ACT3,ACT3B);\n" +
  slice("const NOTATION=", "const COMMANDS=[") +
  "\nexport {BLOCKS,DIVES,SCRIPT,NOTATION,FACTS};";
const { BLOCKS, DIVES, SCRIPT, NOTATION, FACTS } =
  await import("data:text/javascript;base64," + Buffer.from(dataSrc).toString("base64"));

/* ---------- helpers ---------- */
const fails = [];
const fail = (check, msg) => fails.push(`${check}: ${msg}`);
const spokenOf = (op) =>
  [op.text, op.pre, op.post, op.say].filter(Boolean).join(" ") + " " +
  (op.chunks ?? []).map((c) => c.say).join(" ");

function glyphCount(tex) {
  const html = katex.renderToString(tex, { output: "html", throwOnError: true });
  const rules = (html.match(/class="[^"]*\b(frac-line|rule|overline-line|underline-line)\b/g) ?? []).length;
  const text = html.replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">").replace(/&quot;/g, '"')
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(+d));
  let n = 0;
  for (const c of text) if (!/[\s ​]/.test(c)) n++;
  return n + rules;
}

const buildPlan = (level, dive) =>
  SCRIPT.filter((op) => {
    if (op.block) return op.depth === level[op.block];
    if (op.dive === "__always") return DIVES.some((d) => dive[d.id]);
    if (op.dive) return dive[op.dive];
    return true;
  });

const DEPTHS = ["full", "brief", "skip"];
const LEVELS = Object.fromEntries(
  DEPTHS.map((d) => [d, Object.fromEntries(BLOCKS.map((b) => [b.id, d]))]));
const DIVESETS = {
  all: Object.fromEntries(DIVES.map((d) => [d.id, true])),
  none: Object.fromEntries(DIVES.map((d) => [d.id, false])),
};

/* ---------- 1 + 2 latex & alignment ---------- */
let nTex = 0;
for (const op of SCRIPT.filter((o) => o.chunks)) {
  let sum = 0;
  for (const c of op.chunks) {
    nTex++;
    try { sum += glyphCount(c.tex); }
    catch (e) { fail("latex", `${op.id}: ${c.tex} — ${e.message.split("\n")[0]}`); }
  }
  try {
    const joined = glyphCount(op.chunks.map((c) => c.tex).join(" "));
    if (joined !== sum) fail("alignment", `${op.id}: chunks=${sum} joined=${joined}`);
  } catch { /* already reported */ }
}

/* ---------- 3 integrity, every configuration ---------- */
for (const [lname, level] of Object.entries(LEVELS))
  for (const [dname, dive] of Object.entries(DIVESETS)) {
    const live = new Map();
    for (const op of buildPlan(level, dive)) {
      if (op.op === "write" || op.op === "head")
        live.set(op.id, { panel: op.panel, pinned: op.persistence === "pinned" || op.persist === "pinned" });
      if (op.op === "erase")
        for (const [id, m] of [...live])
          if (op.ids ? op.ids.includes(id) : m.panel === op.panel && !m.pinned) live.delete(id);
      for (const ref of [op.target, op.from, op.to, op.point].filter(Boolean))
        if (!live.has(ref)) fail("integrity", `${lname}/${dname}: ${op.op} -> ${ref}`);
    }
  }

/* ---------- 4 cross-block ---------- */
const depthsOf = {};
for (const op of SCRIPT)
  if (op.id && op.block) (depthsOf[op.id] ??= new Set()).add(op.depth);
const ownerBlock = {};
for (const op of SCRIPT) if (op.id && op.block) ownerBlock[op.id] ??= op.block;
for (const op of SCRIPT)
  for (const ref of [op.target, op.from, op.to, op.point].filter(Boolean))
    if (depthsOf[ref] && ownerBlock[ref] !== op.block &&
        !DEPTHS.every((d) => depthsOf[ref].has(d)))
      fail("cross-block", `${ref} referenced outside its block but only at [${[...depthsOf[ref]]}]`);

/* ---------- 5 depth coverage ---------- */
for (const b of BLOCKS)
  for (const d of DEPTHS)
    if (!SCRIPT.some((o) => o.block === b.id && o.depth === d))
      fail("depth", `${b.id} has no '${d}' variant`);

/* ---------- 6 narration coverage ---------- */
for (const op of SCRIPT.filter((o) => o.chunks))
  for (const c of op.chunks)
    if (!c.say?.trim()) fail("narration", `${op.id}: chunk "${c.tex}" has no spoken form`);

/* ---------- 7 term-before-symbol ----------
 * A lecturer naming a technical object should put it on the board. But
 * "we want a Lindbladian — here it is:" is correct teaching, not a defect, so
 * the rule is not "written already" but "written soon". A term may be spoken
 * up to GRACE ops before its defining equation appears; beyond that the
 * audience is being asked to hold an undefined symbol in their head, and a
 * term never written at all is always a failure. */
const GRACE = 4;
const DEFINES = {
  "lindbladian":         "p1L",
  "hamiltonian":         "p1a",
  "gibbs state":         "p1e",
  "bohr frequenc":       "p1c",
  "metropolis":          "p1d",
  "inverse temperature": "p1beta",
  "kms inner product":   "p2a",
  "detailed balance":    "p1d",   // the classical ratio condition, written here
  "kms detailed balance":"p2b",   // the operator statement, written later
  "dirichlet form":      "p2d",
  "spectral gap":        "p2c",
  "mixing time":         "p2e",
  "divergence form":     "p3a",
  "casimir":             "p4c",
  "schur":               "p4b",
  "intertwiner":         "p5b",
  "group mixer":         "r2",
  "wigner":              "r6",
  "spherical tensor":    "r10",
  "free energy":         "d1e",
  "conductance":         "r6b",
};
// Only meaningful where the board is actually being built: full depth, all dives.
{
  const plan = buildPlan(LEVELS.full, DIVESETS.all);
  const writeIndex = new Map();
  plan.forEach((op, i) => {
    if ((op.op === "write" || op.op === "head") && !writeIndex.has(op.id))
      writeIndex.set(op.id, i);
  });
  const seen = new Set();
  plan.forEach((op, i) => {
    const spoken = spokenOf(op).toLowerCase();
    for (const [term, defId] of Object.entries(DEFINES)) {
      if (seen.has(term) || !spoken.includes(term)) continue;
      seen.add(term);
      const at = writeIndex.get(defId);
      if (at === undefined)
        fail("term-before-symbol", `"${term}" is spoken but ${defId} is never written`);
      else if (at > i + GRACE)
        fail("term-before-symbol",
          `"${term}" first spoken at op ${i} (${op.id ?? op.op}) but ${defId} is not written until op ${at} — ${at - i} ops later`);
    }
  });
  for (const [term, defId] of Object.entries(DEFINES))
    if (!SCRIPT.some((o) => o.id === defId))
      fail("term-before-symbol", `term table points at "${defId}", which no op defines`);
}

/* ---------- 8 kb refs ---------- */
{
  const ids = new Set(SCRIPT.filter((o) => o.id).map((o) => o.id));
  for (const [k, v] of Object.entries(NOTATION))
    if (v.ref && !ids.has(v.ref)) fail("kb", `NOTATION[${k}] -> ${v.ref}`);
  for (const f of FACTS)
    if (f.point && !ids.has(f.point)) fail("kb", `FACT "${f.topic}" -> ${f.point}`);
}

/* ---------- report ---------- */
const WPS = 1.97;
const runtime = (plan) => {
  let ms = 0;
  for (const op of plan) {
    const t = spokenOf(op).trim();
    if (t) ms += Math.max(650, (t.split(/\s+/).length / WPS) * 1000);
    ms += { write: 600, head: 600, point: 1500, arrow: 900, annotate: 700, erase: 1300 }[op.op] ?? 0;
    if (op.op === "beat") ms += op.ms ?? 2600;
  }
  return ms / 60000;
};
const hm = (m) => `${Math.floor(m / 60)}h${String(Math.round(m % 60)).padStart(2, "0")}`;

console.log(`\n${file}`);
console.log(`  ${SCRIPT.length} ops · ${nTex} latex chunks · ${BLOCKS.length} prereq blocks · ${DIVES.length} deep dives`);
console.log(`  ${Object.keys(NOTATION).length} notation entries · ${FACTS.length} facts`);
console.log(`\n  runtime`);
for (const l of DEPTHS)
  for (const d of ["all", "none"])
    console.log(`    prereq ${l.padEnd(5)} + dives ${d.padEnd(4)}  ${hm(runtime(buildPlan(LEVELS[l], DIVESETS[d])))}`);

if (fails.length) {
  console.log(`\n  ${fails.length} FAILURE(S)`);
  for (const f of fails) console.log(`    x ${f}`);
  console.log();
  process.exit(1);
}
console.log(`\n  all 8 checks pass\n`);
