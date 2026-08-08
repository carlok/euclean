"""SECRET-SIDE. Read the findings back in real vocabulary.

Everything the pipeline produces is anonymous by construction. At some point a
human has to ask what it actually found, and that requires the translation table
the pipeline is forbidden to see. This tool does that, and it lives in `tools/`
rather than `pipeline/` for exactly that reason: the quarantine forbids
`pipeline/` from reaching into `secret/`, not the operator's own scripts.

Its output goes to `secret/` and must never be committed or quoted outward.

Three things are produced, in increasing order of interest.

**A verification nobody has run.** The canonical relation names are the basis of
every cross-run comparison in this project, and their correctness has only ever
been argued structurally: `Rel4_0` is supposed to mean the same relation in
every run regardless of how that run permuted its identifiers. Composing each
member's canonical map with its seed's translation table turns that into
something checkable against ground truth. If a canonical name resolves to two
different real relations across seeds, every survival number is meaningless, and
until now nothing would have said so.

**The findings, translated.** The statements the importance measure promotes,
written in the vocabulary a mathematician would use.

**The withheld concepts, graded.** Each notion deliberately kept out of the
system, marked according to whether anything the miner proposed matches it. This
is the only place the concept-invention result can be read as mathematics rather
than as a survival count.

Usage:
  python3 tools/deanonymize.py --theory t0f85211
"""

import argparse
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECRET = ROOT / "secret"
sys.path.insert(0, str(SECRET))

try:
    import theory_codes as codes  # noqa: E402
    import theory_spec as spec  # noqa: E402
except ImportError:
    sys.exit("deanonymize: secret/ is absent, so there is nothing to translate with")

sys.path.insert(0, str(ROOT))
from pipeline.ensemble import grids, stability  # noqa: E402


def seed_map_for(domain, seed):
    """The translation table, trying both the current and the legacy filename."""
    for stem in (domain, *[r for r, d in spec.LEGACY_ROLES.items() if d == domain]):
        p = SECRET / "seed_maps" / f"{stem}-seed{seed}.json"
        if p.exists():
            return json.loads(p.read_text())
    return None


def canonical_to_real(theory, domain):
    """canonical relation name -> real name, resolved through every seed.

    Each member records the map from its own anonymized symbols to canonical
    names; each seed's table maps those symbols to real ones. Composing them
    gives canonical -> real, and doing it for every seed independently is the
    check: they must all agree.
    """
    votes = defaultdict(set)
    seeds_seen = set()
    for summary in grids.summaries(theory=theory, base_seed=grids.ANY):
        seed = summary.get("theory_seed")
        table = seed_map_for(domain, seed)
        if not table:
            continue
        seeds_seen.add(seed)
        for anon, canon in (summary.get("relation_canonical_map") or {}).items():
            real = table["relations"].get(anon)
            if real:
                votes[canon].add(real)

    conflicts = {c: sorted(v) for c, v in votes.items() if len(v) > 1}
    return {c: sorted(v)[0] for c, v in votes.items()}, conflicts, sorted(seeds_seen)


def translate(text, mapping):
    """Rewrite canonical relation names in a rendered statement."""
    for canon, real in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(canon, real)
    return text


def _relations_in(formula, out=None):
    """Every relation symbol occurring in a stored formula."""
    out = set() if out is None else out
    if isinstance(formula, dict):
        if formula.get("kind") == "atom":
            out.add(formula.get("rel"))
        for v in formula.values():
            _relations_in(v, out)
    elif isinstance(formula, list):
        for v in formula:
            _relations_in(v, out)
    return out


def _concepts_in_real_names(theory, domain):
    """Every ranked concept, with its relations resolved to real names.

    Done per member because each member permutes the symbols differently.
    """
    out = []
    for d in grids.member_dirs(theory=theory, base_seed=grids.ANY):
        summary = json.loads((d / "summary.json").read_text())
        table = seed_map_for(domain, summary.get("theory_seed"))
        if not table:
            continue
        concepts = json.loads((d / "concepts.json").read_text())["ranked"]
        for c in concepts:
            anon = _relations_in(c.get("body") or c.get("statement_ast") or {})
            real = {table["relations"][a] for a in anon if a in table["relations"]}
            if real:
                out.append({"survives": 1, "relations": real})
    return out


def grade_withheld(domain, concepts_seen):
    """Could the miner have proposed each withheld notion at all?

    An earlier version of this counted candidates ranging over the same
    relations. That is uninformative in both directions: a bug made it report 0
    for everything, which read as a clean negative, and fixing the bug made it
    report thousands, which reads as nothing. Relation overlap is not evidence.

    The decisive question is prior to search. The miner has three languages:
    conjunctions of premises, patterns mined from proof structure, and
    existentially quantified conjunctions. None of them can express a
    disjunction. So a withheld notion defined by cases was never reachable, and
    reporting it as "not found" would blame the search for a limit of the
    language.
    """
    withheld = spec.THEORIES[domain]["withheld_concepts"]
    rels = set(spec.THEORIES[domain]["relations"])
    rows = []
    for name, definition in withheld.items():
        needed = sorted(r for r in rels if r in definition)
        disjunctive = "∨" in definition or " or " in definition
        existential = "∃" in definition
        if disjunctive:
            verdict, why = "unreachable", "defined by cases; no candidate language has a disjunction"
        elif not needed:
            verdict, why = "not primitive", "not defined directly over the relations"
        elif existential:
            verdict, why = "reachable", "expressible by the quantified source"
        else:
            verdict, why = "reachable", "expressible as a conjunction of premises"
        rows.append(
            {
                "concept": name,
                "definition": definition,
                "over": needed,
                "verdict": verdict,
                "why": why,
            }
        )
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theory", default=None, help="theory code; defaults to the subject")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    theory = args.theory or grids.subject()
    domain = next((d for d in spec.THEORIES if codes.code(d) == theory), None)
    if domain is None:
        sys.exit(f"deanonymize: no domain maps to code {theory!r}")

    mapping, conflicts, seeds = canonical_to_real(theory, domain)

    L = [f"# SECRET — findings for {domain} ({theory}), read back",
         "",
         "Generated by `tools/deanonymize.py`. Never commit, never quote outward.",
         ""]

    L.append("## Canonical names verified against ground truth")
    L.append("")
    L.append(f"Resolved through {len(seeds)} independent identifier permutations "
             f"(seeds {seeds}).")
    L.append("")
    if conflicts:
        L.append("**FAILED.** A canonical name resolves to more than one real relation, so")
        L.append("cross-run comparison for this theory is not valid:")
        L.append("")
        for c, reals in conflicts.items():
            L.append(f"- `{c}` -> {reals}")
    else:
        L.append("Every canonical name resolves to exactly one real relation in every")
        L.append("permutation. The cross-run identity the survival numbers rest on holds.")
        L.append("")
        for canon, real in sorted(mapping.items()):
            L.append(f"- `{canon}` = **{real}**")
    L.append("")

    members = stability.load_members(theory=theory)
    if members:
        rows = stability.top_statement_survival(members, top=15)
        L.append("## What the importance measure promoted")
        L.append("")
        L.append(f"Top {args.top} by survival across {len(members)} configurations.")
        L.append("")
        L.append("| survives | statement |")
        L.append("|---|---|")
        for r in rows[: args.top]:
            L.append(f"| {r['survives']}/{r['of']} | `{translate(r['statement'], mapping)}` |")
        L.append("")

        # Concept bodies carry each member's OWN anonymized symbols, not the
        # canonical names, so they have to be translated per member through that
        # member's seed table. Scanning them for canonical names finds nothing
        # and reports a clean zero for every withheld concept -- a vacuous
        # result indistinguishable from a real one.
        seen = _concepts_in_real_names(theory, domain)
        L.append("## Withheld concepts")
        L.append("")
        L.append("Whether the miner's language can express each notion at all, which is")
        L.append("prior to whether the search found it. A notion defined by cases was")
        L.append("never reachable, and calling it *not found* would blame the search for")
        L.append("a limit of the language.")
        L.append("")
        L.append("| withheld | over | reachable? | why |")
        L.append("|---|---|---|---|")
        for g in grade_withheld(domain, seen):
            L.append(
                f"| {g['concept']} | {', '.join(g['over']) or '—'} | "
                f"{g['verdict']} | {g['why']} |"
            )
        L.append("")

    out = SECRET / f"deanon-{theory}.md"
    out.write_text("\n".join(L) + "\n")
    print(f"canonical names: {'CONFLICT' if conflicts else 'consistent'} over seeds {seeds}")
    for canon, real in sorted(mapping.items()):
        print(f"  {canon} = {real}")
    print(f"wrote {out.relative_to(ROOT)}  (SECRET)")


if __name__ == "__main__":
    main()
