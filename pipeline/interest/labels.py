"""Ground truth for the audit: which statements are restatements.

Every label is decided by existing euclean code paths and by the proof DAG
alone, and it is fixed and hashed before any interestingness score exists.
Tiers, checked in this order, and the first that fires is the label:

R0, exact
    The canonical form (`canon.normalize.key`) of the statement equals that of
    an axiom or of an earlier corpus statement, or of the universal closure of
    one of their conclusions. The chainer already drops exact duplicates and
    axiom restatements (`chainer/filters.assess`), and `concepts/roles.py`
    skips any candidate whose key is already known ("a restatement, not a
    step"); this tier applies the same key test to the corpus itself.
R1, single-axiom
    The transitive footprint (`reverse.footprint`) is exactly one axiom `a`, and
    the statement is an instance of `a`: some substitution of `a`'s universal
    variables, up to the order of binders and hypotheses (the canonicalisation),
    yields the statement. Sufficiency of `{a}` is checked the way
    `reverse.verify` checks it: the axioms the stored proof cites, transitively,
    are a subset of `{a}`, the proof re-infers against the theory restricted to
    `{a}` (`reverse.minimise.Restricted`) plus the lemmas it cites, and Lean has
    accepted the proof.
R2, propagated
    The sprint-3 check (`concepts.invent.score`, "axioms_in_every_user"): group
    statements by the abstracted shape of their conclusion; a statement is R2
    when an axiom concludes that same shape and every statement in the group
    cites that axiom directly. "Every supporting proof cites the axiom whose
    conclusion it is."
N
    None of the above.

A secondary tier, R1fp, records footprint size one without the instance test.
It is reported alongside, never substituted.
"""

import hashlib
import json
from collections import defaultdict

from ..canon import normalize as N
from ..concepts import invent
from ..kernel import formula as F, proof as P
from ..reverse import footprint as footprint_mod
from ..reverse import minimise, verify as reverse_verify

TIERS = ("R0", "R1", "R2", "N")
RESTATEMENT = ("R0", "R1", "R2")


# --- shapes ---------------------------------------------------------------


def split(stmt):
    """(binders, premises, conclusion) of a ∀-prefixed implication chain."""
    if stmt["kind"] == "forall":
        binders, body = list(stmt["vars"]), stmt["body"]
    else:
        binders, body = [], stmt
    ps, concl = F.premises(body)
    return binders, ps, concl


def closure_of_conclusion(stmt):
    """∀ (the conclusion's free variables, in binder order), conclusion."""
    binders, _, concl = split(stmt)
    free = F.free_vars(concl)
    kept = [v for v in binders if v in free]
    return F.Forall(kept, concl) if kept else concl


def conclusion_shape(stmt):
    """The key `concepts.invent` groups conclusions by."""
    body, _ = invent.abstract(N.canonical(invent._conclusion(stmt)))
    return repr(F.key(body))


# --- matching for R1 ------------------------------------------------------


def _match(p, t, sub, bound, pvars):
    """Extend `sub` so that p, with pattern variables `pvars`, becomes t.

    `bound` pairs bound variables of p with those of t. Structural: no
    reordering of conjuncts or disjuncts, which instantiation never does.
    """
    k = p["kind"]
    if k != t["kind"]:
        return None
    if k == "var":
        name = p["name"]
        if name in bound:
            return sub if bound[name] == t["name"] else None
        if name in pvars:
            have = sub.get(name)
            if have is None:
                if t["name"] in bound.values():
                    return None  # would capture a bound variable of t
                out = dict(sub)
                out[name] = t["name"]
                return out
            return sub if have == t["name"] else None
        return sub if name == t["name"] else None
    if k == "const":
        return sub if p["name"] == t["name"] else None
    if k == "atom":
        if p["rel"] != t["rel"] or len(p["args"]) != len(t["args"]):
            return None
        for a, b in zip(p["args"], t["args"]):
            sub = _match(a, b, sub, bound, pvars)
            if sub is None:
                return None
        return sub
    if k == "eq":
        sub = _match(p["lhs"], t["lhs"], sub, bound, pvars)
        return None if sub is None else _match(p["rhs"], t["rhs"], sub, bound, pvars)
    if k == "not":
        return _match(p["arg"], t["arg"], sub, bound, pvars)
    if k in F.BINARY:
        sub = _match(p["lhs"], t["lhs"], sub, bound, pvars)
        return None if sub is None else _match(p["rhs"], t["rhs"], sub, bound, pvars)
    if k in F.QUANT:
        if len(p["vars"]) != len(t["vars"]):
            return None
        inner = dict(bound)
        inner.update(zip(p["vars"], t["vars"]))
        return _match(p["body"], t["body"], sub, inner, pvars)
    raise ValueError(k)


def instance_substitutions(axiom, stmt):
    """Every substitution of the axiom's variables that yields the statement,
    as checked by canonical key. Usually zero or one."""
    a_vars, a_ps, a_concl = split(axiom)
    t_vars, t_ps, t_concl = split(stmt)
    pvars = set(a_vars)
    base = _match(a_concl, t_concl, {}, {}, pvars)
    if base is None:
        return []
    target = N.key(stmt)
    found = []

    def assign(i, sub):
        if i == len(a_ps):
            if not pvars <= set(sub):
                return
            inst = F.subst(axiom["body"] if axiom["kind"] == "forall" else axiom,
                           {v: F.Var(n) for v, n in sub.items()})
            cand = F.Forall(t_vars, inst) if t_vars else inst
            if N.key(cand) == target:
                found.append(dict(sub))
            return
        for tp in t_ps:
            ext = _match(a_ps[i], tp, sub, {}, pvars)
            if ext is not None:
                assign(i + 1, ext)

    assign(0, base)
    return found


# --- the tiers ------------------------------------------------------------


def label_corpus(records, theory, lean_accepted):
    """One label per record, with the rule that fired and its evidence.

    `lean_accepted` says whether Lean accepted the stored proofs; it is part of
    the R1 sufficiency check and is recorded, never assumed.
    """
    axiom_names = list(theory.axiom_names)
    axioms = dict(theory.env)
    by_id = {r["id"]: r for r in records}

    foot, missing = footprint_mod.footprints(records, axiom_names)
    if missing:
        raise ValueError(f"cited lemmas absent from the corpus: {sorted(missing)[:5]}")

    # R0: keys of axioms and of their conclusions' closures; earlier statements
    # are added as the loop below passes them
    known = {}
    for name, stmt in axioms.items():
        known.setdefault(N.key(stmt), name)
        known.setdefault(N.key(closure_of_conclusion(stmt)), name)

    # R2: conclusion shapes, and which axioms every holder of a shape cites
    shape_of = {r["id"]: conclusion_shape(r["statement_ast"]) for r in records}
    holders = defaultdict(list)
    for r in records:
        holders[shape_of[r["id"]]].append(r["id"])
    axiom_shapes = defaultdict(set)
    for name, stmt in axioms.items():
        axiom_shapes[conclusion_shape(stmt)].add(name)
    in_every = {}
    for shape, ids in holders.items():
        if shape not in axiom_shapes:
            continue
        body, params = invent.abstract(N.canonical(invent._conclusion(by_id[ids[0]]["statement_ast"])))
        cand = {"body": body, "params": params, "theorems": ids, "support": len(ids)}
        in_every[shape] = set(invent.score(cand, by_id, {})["axioms_in_every_user"])

    out = []
    for r in records:
        rid, stmt = r["id"], r["statement_ast"]
        fp = foot[rid]
        fired = []
        evidence = {}

        k = N.key(stmt)
        if k in known:
            fired.append("R0")
            evidence["R0"] = {"matches": known[k]}

        if len(fp) == 1:
            a = fp[0]
            subs = instance_substitutions(axioms[a], stmt)
            if subs:
                cited, miss = reverse_verify.cited_axioms(r, records, axiom_names)
                restricted = minimise.Restricted(theory, {a})
                env = dict(restricted.env)
                for lem in P.references(r["proof_ast"]):
                    if lem in by_id:
                        env[lem] = by_id[lem]["statement_ast"]
                try:
                    reinfers = F.same(P.infer(r["proof_ast"], env), stmt)
                except P.ProofError:
                    reinfers = False
                sufficient = set(cited) <= {a} and not miss and reinfers and lean_accepted
                if sufficient:
                    fired.append("R1")
                evidence["R1"] = {
                    "axiom": a,
                    "substitution": subs[0],
                    "cited_axioms": cited,
                    "reinfers_restricted": reinfers,
                    "lean_accepted": lean_accepted,
                    "sufficient": sufficient,
                }

        shape = shape_of[rid]
        hits = sorted(axiom_shapes.get(shape, set()) & in_every.get(shape, set()))
        if hits:
            fired.append("R2")
            evidence["R2"] = {"axiom": hits[0], "group_size": len(holders[shape])}

        label = next((t for t in RESTATEMENT if t in fired), "N")
        out.append(
            {
                "id": rid,
                "label": label,
                "rule": label,
                "fired": fired,
                "footprint": fp,
                "R1fp": len(fp) == 1,
                "generation": r["generation"],
                "evidence": evidence,
            }
        )
        # only *earlier* statements count for R0, so the statement joins the
        # known set after it has been checked against it
        known.setdefault(k, rid)
        known.setdefault(N.key(closure_of_conclusion(stmt)), rid)
    return out


def write_labels(rows, path):
    text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def read_labels(path, expect_sha256=None):
    text = path.read_text()
    got = hashlib.sha256(text.encode()).hexdigest()
    if expect_sha256 is not None and got != expect_sha256:
        raise ValueError(f"labels at {path} changed since they were frozen: {got}")
    return [json.loads(line) for line in text.splitlines() if line.strip()], got


def label_run(run, log=print):
    from ..kernel import theory as theory_mod
    from ..kernel.theory import ROOT

    run_dir = ROOT / "runs" / run
    summary = json.loads((run_dir / "summary.json").read_text())
    spec = json.loads((ROOT / summary["spec_path"]).read_text())
    T = theory_mod.Theory(spec)
    records = json.loads((run_dir / "corpus.json").read_text())
    accepted = bool(summary.get("lean_modules")) and all(r.get("verification") for r in records)
    rows = label_corpus(records, T, accepted)
    sha = write_labels(rows, run_dir / "interest" / "labels.jsonl")
    counts = {t: sum(1 for r in rows if r["label"] == t) for t in TIERS}
    log(f"{run}: {len(rows)} labelled {counts}  sha256 {sha}")
    return sha


def main():
    """Label every pre-registered corpus and write the hash manifest."""
    import argparse

    from . import plan

    ap = argparse.ArgumentParser()
    ap.add_argument("--run", nargs="*", default=None)
    args = ap.parse_args()
    runs = args.run or plan.corpora()
    hashes = {run: label_run(run) for run in runs}
    if args.run is None:
        lines = ["# sha256 of runs/<run>/interest/labels.jsonl, frozen before any score was computed"]
        lines += [f"{hashes[r]}  {r}" for r in runs]
        plan.LABEL_MANIFEST.write_text("\n".join(lines) + "\n")
        print(f"wrote {plan.LABEL_MANIFEST}")


if __name__ == "__main__":
    main()
