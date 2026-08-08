"""Corpus driver: saturate, filter, verify, promote, repeat.

Promotion is what gives the corpus depth. A single saturation pass over the
axioms bottoms out quickly — the interesting statements need a lemma that an
earlier pass had to prove first. So each generation's surviving theorems are
folded back into the rule set, and the next pass gets to use them.

Generation g may cite anything from generations < g and nothing from its own,
so batches within a generation stay independent and check in parallel, while
the import graph between generations stays a simple chain.
"""

import argparse
import json
import pathlib
import time
from collections import Counter

from ..canon import normalize as N
from ..kernel import emit, formula as F, proof as P, theory as theory_mod, verify
from . import filters
from .engine import Engine

ROOT = pathlib.Path(__file__).resolve().parents[2]


def promotion_score(stmt, pf):
    """Prefer statements that can actually drive later derivations."""
    premises, concl = filters._split(stmt)
    score = 0.0
    if concl["kind"] == "atom":
        score += 3.0
    elif concl["kind"] == "eq":
        score += 2.0
    elif concl["kind"] == "exists":
        score += 1.0
    score += min(len(premises), 3) * 0.5
    score -= 0.05 * F.size(stmt)
    score -= 0.02 * P.size(pf)
    return score


def build(theory, seed=0, generations=3, cfg=None, promote_max=60,
          existential_cap=200, extra_env=None, log=print):
    axiom_keys = filters.axiom_key_set(theory)
    # atoms the axioms forbid outright; a premise instantiating one makes the
    # statement vacuously true, kernel-verified and empty
    refuted = filters.refuted_premises(theory)
    seen = set(axiom_keys)
    records, items_by_gen = [], []
    # Seeded rules (invented concepts under ablation, say) start in the
    # environment and promotion adds to them from there.
    extra_env = dict(extra_env or {})
    rejected = Counter()
    traces = []

    for g in range(generations):
        eng = Engine(theory, cfg, seed=seed + g, extra_env=extra_env)
        trace = eng.saturate()
        traces.append({"generation": g, "rounds": trace, "rules": len(eng.rules)})

        # The engine's own counters. These existed but were dropped on the floor:
        # `rejected` below collects filter reasons only, so no budget cap has
        # ever reached a published artifact. Prefixed to keep the two kinds
        # apart — a statement refused by a filter and a derivation never
        # attempted because a cap was hit are different facts about a run.
        for reason, count in eng.rejected.items():
            rejected[f"engine:{reason}"] += count

        raw = []
        for fact in eng.facts.values():
            try:
                raw.append(eng.extract(fact) + (fact,))
            except Exception as exc:  # a malformed term is a bug, not a result
                rejected[f"extract-error:{type(exc).__name__}"] += 1

        # Fewest hypotheses first. The weakening filter compares a statement
        # against stronger forms already recorded, so the strong form has to be
        # assessed before the padded ones it should suppress.
        raw.sort(key=lambda x: (len(filters._split(x[0])[0]), F.size(x[0])))

        fresh = []
        for stmt, pf, fact in raw:
            keep, reason = filters.assess(stmt, axiom_keys, seen, refuted)
            if not keep:
                rejected[reason] += 1
                continue
            seen.add(N.key(stmt))
            fresh.append((stmt, pf, fact))

        # Existential conclusions outnumber everything else by an order of
        # magnitude and are mostly weak — "some configuration exists" with the
        # hypotheses along for the ride. Capping them per generation keeps the
        # corpus from drowning without discarding a single statement that has
        # no existential in it. The cap shows up in the rejection log like any
        # other filter, so the trade-off stays visible.
        fresh.sort(key=lambda x: -promotion_score(x[0], x[1]))
        kept, ex_seen = [], 0
        for stmt, pf, fact in fresh:
            _, concl = filters._split(stmt)
            if concl["kind"] == "exists":
                ex_seen += 1
                if ex_seen > existential_cap:
                    rejected["quota-existential"] += 1
                    continue
            kept.append((stmt, pf, fact))
        fresh = kept

        gen_items = []
        for i, (stmt, pf, fact) in enumerate(fresh):
            name = f"t{g}_{i:05d}"
            gen_items.append((name, stmt, pf))
            refs = P.references(pf)
            records.append(
                {
                    "id": name,
                    "generation": g,
                    "statement": emit.formula(stmt, top=True),
                    "normalized_statement": emit.formula(N.canonical(stmt), top=True),
                    "statement_ast": stmt,
                    "proof_ast": pf,
                    "axiom_dependencies": sorted(k for k in refs if k in theory.env),
                    "proof_dependencies": sorted(k for k in refs if k not in theory.env),
                    "proof_size": P.size(pf),
                    "proof_depth": P.depth(pf),
                    "proof_nodes": P.node_counts(pf),
                    "proof_branching": P.branching(pf),
                    "generation_method": fact.origin,
                    "why_kept": "survived filters",
                    "verification": False,
                }
            )
        items_by_gen.append(gen_items)
        log(f"  generation {g}: {len(gen_items)} kept, {sum(rejected.values())} rejected so far")

        promoted = [(n, s) for n, s, _ in gen_items if s["kind"] == "forall"]
        extra_env = {**extra_env, **dict(promoted[:promote_max])}

    return records, items_by_gen, dict(rejected), traces


def verify_corpus(items_by_gen, log=print, theory=None):
    """Check every generation, chaining imports so later ones can cite earlier."""
    return verify_corpus_with(items_by_gen, ["Theory.Anonymous"], log=log, theory=theory)


def verify_corpus_with(items_by_gen, base_imports, log=print, theory=None):
    # Refuse to check a corpus against a base module built from other axioms.
    # The generator rewrites theory/ in place, so with more than one theory
    # around this is reachable, and the symptom would be every batch rejected —
    # indistinguishable from a theory that derives nothing.
    if theory is not None:
        verify.assert_theory_matches(theory)
    verify.clear_batches()
    batch_no = 0
    imports = list(base_imports)
    failures = []
    for g, items in enumerate(items_by_gen):
        if not items:
            continue
        paths = []
        for i in range(0, len(items), verify.BATCH_SIZE):
            paths.append(
                verify.write_batch(batch_no, items[i : i + verify.BATCH_SIZE], imports=imports)
            )
            batch_no += 1
        bad = [(p, log_) for p, ok, log_ in verify.check_files(paths) if not ok]
        failures.extend(bad)
        log(f"  generation {g}: {len(paths)} batches, {len(bad)} rejected")
        imports = imports + [f"Theory.{p.stem}" for p in paths]
        if bad:
            break
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--generations", type=int, default=3)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--no-distinct", action="store_true",
                    help="drop the assumed pairwise-distinctness hypotheses")
    args = ap.parse_args()

    T = theory_mod.load()
    run_id = args.run_id or f"seed{args.seed}-g{args.generations}"
    out = ROOT / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)

    print(f"run {run_id}: {T}")
    t0 = time.time()
    cfg = {"assume_distinct": False} if args.no_distinct else None
    records, items_by_gen, rejected, traces = build(
        T, seed=args.seed, generations=args.generations, cfg=cfg
    )
    t_gen = time.time() - t0
    print(f"generated {len(records)} candidates in {t_gen:.1f}s")

    t1 = time.time()
    failures = [] if args.no_verify else verify_corpus(items_by_gen)
    t_ver = time.time() - t1
    if failures:
        print(f"KERNEL REJECTED {len(failures)} batch(es)")
        for path, log_ in failures[:1]:
            print("\n".join(log_.splitlines()[:15]))
    else:
        for r in records:
            r["verification"] = not args.no_verify
        print(f"kernel-checked in {t_ver:.1f}s")

    write_artifacts(records, out, rejected, traces, t_gen, t_ver, args, T)
    print(f"wrote {out}")


def write_artifacts(records, out, rejected, traces, t_gen, t_ver, args, T):
    gen_dir, meta_dir = ROOT / "generated", ROOT / "metadata"
    for d in (gen_dir, meta_dir):
        for old in d.glob("theorem_*"):
            old.unlink()

    for i, r in enumerate(records):
        stem = f"theorem_{i:06d}"
        (gen_dir / f"{stem}.lean").write_text(
            emit.theorem(r["id"], r["statement_ast"], r["proof_ast"])
        )
        slim = {k: v for k, v in r.items() if not k.endswith("_ast")}
        (meta_dir / f"{stem}.json").write_text(json.dumps(slim, indent=1) + "\n")

    (out / "corpus.json").write_text(json.dumps(records) + "\n")
    (out / "summary.json").write_text(
        json.dumps(
            {
                "run": out.name,
                "theory_seed": T.seed,
                "chainer_seed": args.seed,
                "generations": args.generations,
                "kept": len(records),
                "rejected": rejected,
                "traces": traces,
                "seconds_generate": round(t_gen, 2),
                "seconds_verify": round(t_ver, 2),
            },
            indent=1,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
