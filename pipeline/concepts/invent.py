"""Propose and score candidate definitions.

The brief's working hypothesis is that a good mathematical concept compresses
and organizes proofs. That is the thing under test, so the scorer reports each
criterion separately and never collapses them into a single number — a concept
that compresses the text but unifies nothing, or unifies clusters but saves no
description length, is a result worth seeing rather than an average worth
hiding.

Candidates come from recurring conjunctions of hypotheses that share variables.
Frequency alone is explicitly not sufficient grounds for accepting one; it only
decides what gets scored.

Definitions are emitted as definitional extensions, so the enriched theory is
conservative over the original by construction and the iterative loop's
requirement that T_{i+1} extend T_i holds without anyone having to check it.
"""

import json
from collections import Counter, defaultdict

from ..canon import normalize as N
from ..kernel import formula as F


def abstract(formula):
    """Replace every variable by a positional parameter, in first-occurrence
    order. Two hypothesis pairs that differ only in their variable names then
    land on the same pattern, while ones that share variables differently do
    not."""
    order, mapping = [], {}

    def walk(f):
        k = f["kind"]
        if k == "var":
            if f["name"] not in mapping:
                mapping[f["name"]] = f"x{len(order)}"
                order.append(f["name"])
            return
        if k == "atom":
            for a in f["args"]:
                walk(a)
        elif k == "eq":
            walk(f["lhs"])
            walk(f["rhs"])
        elif k == "not":
            walk(f["arg"])
        elif k in F.BINARY:
            walk(f["lhs"])
            walk(f["rhs"])
        elif k in F.QUANT:
            walk(f["body"])

    walk(formula)
    body = F.subst(formula, {v: F.Var(p) for v, p in zip(order, [f"x{i}" for i in range(len(order))])})
    return body, [f"x{i}" for i in range(len(order))]


def _premises(stmt):
    body = stmt["body"] if stmt["kind"] == "forall" else stmt
    return F.premises(body)[0]


def _conclusion(stmt):
    body = stmt["body"] if stmt["kind"] == "forall" else stmt
    concl = F.premises(body)[1]
    return concl["body"] if concl["kind"] == "exists" else concl


def disjunctive_candidates(records, min_support, max_params):
    """Recurring disjunctions, mined from conclusions.

    Sprint 1 could not have found these: it mined conjunctions of hypotheses
    only, and in any case its corpus contained no disjunction at all. Both gaps
    are closed now, which matters because a defined notion can perfectly well be
    a disjunction, and one that is will never turn up in a conjunction-only
    search however long it runs.

    A caution that belongs with the result rather than after it: a disjunction
    that recurs only because one axiom concludes it is a restatement of that
    axiom, not an invention. `score` reports `distinct_axiom_profiles`, and the
    evaluation should hold any disjunctive concept to it.
    """
    support = Counter()
    holders = defaultdict(set)
    shapes = {}

    for r in records:
        concl = _conclusion(r["statement_ast"])
        if concl["kind"] != "or":
            continue
        body, params = abstract(N.canonical(concl))
        if len(params) > max_params:
            continue
        key = repr(F.key(body))
        support[key] += 1
        holders[key].add(r["id"])
        shapes[key] = (body, params)

    return [
        {
            "key": k,
            "body": shapes[k][0],
            "params": shapes[k][1],
            "support": v,
            "theorems": sorted(holders[k]),
            "source": "conclusion-disjunction",
        }
        for k, v in support.items()
        if v >= min_support
    ]


def candidates(records, min_support=8, max_params=6, max_conjuncts=3):
    """Recurring variable-sharing conjunctions of hypotheses."""
    support = Counter()
    holders = defaultdict(set)
    shapes = {}

    for r in records:
        ps = _premises(r["statement_ast"])
        if len(ps) < 2:
            continue
        for width in range(2, min(max_conjuncts, len(ps)) + 1):
            for combo in _combinations(ps, width):
                shared = set(F.free_vars(combo[0]))
                joined = set()
                for c in combo[1:]:
                    joined |= F.free_vars(c)
                if not (shared & joined):
                    continue  # disjoint hypotheses are not a concept
                # right-nested, matching how Lean parses `A ∧ B ∧ C`, so that
                # the currying and the `.left`/`.right` paths in the bridge
                # lemmas line up with the definition without special cases
                conj = combo[-1]
                for c in reversed(combo[:-1]):
                    conj = F.And(c, conj)
                body, params = abstract(N.canonical(conj))
                if len(params) > max_params:
                    continue
                key = repr(F.key(body))
                support[key] += 1
                holders[key].add(r["id"])
                shapes[key] = (body, params)

    out = [
        {"key": k, "body": shapes[k][0], "params": shapes[k][1], "support": v,
         "theorems": sorted(holders[k]), "source": "premise-conjunction"}
        for k, v in support.items()
        if v >= min_support
    ]
    out.extend(disjunctive_candidates(records, min_support, max_params))
    return out


def _combinations(items, width):
    import itertools

    return itertools.combinations(items, width)


def score(cand, records_by_id, assignments, method="kmeans_numeric"):
    """Every criterion reported on its own terms."""
    body, params = cand["body"], cand["params"]
    occurrences = len(cand["theorems"])

    # description length: each use replaces a conjunction of size S by an
    # application of arity k; the definition itself has to be paid for once
    s = F.size(body)
    per_use_saving = s - (1 + len(params))
    definition_cost = s + len(params)
    dl_reduction = occurrences * per_use_saving - definition_cost

    clusters = {assignments[t][method] for t in cand["theorems"] if t in assignments}

    proofs = set()
    generations = set()
    common_axioms = None
    for t in cand["theorems"]:
        r = records_by_id[t]
        proofs.add(tuple(sorted(r["axiom_dependencies"])))
        generations.add(r["generation"])
        axs = set(r["axiom_dependencies"])
        common_axioms = axs if common_axioms is None else (common_axioms & axs)
    common_axioms = sorted(common_axioms or ())

    sizes = [records_by_id[t]["proof_size"] for t in cand["theorems"]]

    return {
        "source": cand.get("source", "premise-conjunction"),
        "support": cand["support"],
        "theorems_covered": occurrences,
        "conjuncts": _conjunct_count(body),
        "arity": len(params),
        "body_size": s,
        "per_use_saving": per_use_saving,
        "description_size_reduction": dl_reduction,
        "clusters_unified": len(clusters),
        "distinct_axiom_profiles": len(proofs),
        # Axioms every single user's proof cites. A pattern that recurs widely
        # but always behind the same axiom is that axiom showing through, not an
        # abstraction the corpus independently motivates. This is the difference
        # between inventing a concept and restating a hypothesis, and it is not
        # visible from support counts or cluster spread — both of which can look
        # excellent for something wholly explained by one axiom.
        "axioms_in_every_user": common_axioms,
        "independent_of_any_single_axiom": not common_axioms,
        "generations_spanned": len(generations),
        "mean_proof_size_of_users": round(sum(sizes) / len(sizes), 1) if sizes else 0,
    }


def _conjunct_count(body):
    n = 1
    while body["kind"] == "and":
        n += 1
        body = body["rhs"]
    return n


def emit_definition(name, body, params, sort="Obj"):
    from ..kernel import emit

    binders = " ".join(f"({p} : {sort})" for p in params)
    return f"def {name} {binders} : Prop :=\n  {emit.formula(body, top=True)}\n"


def conjuncts(body):
    out = []
    while body["kind"] == "and":
        out.append(body["lhs"])
        body = body["rhs"]
    out.append(body)
    return out


def emit_bridges(name, body, params, sort="Obj"):
    """Introduction and elimination lemmas for a definitional extension.

    The introduction rule is emitted *curried* — `P1 → P2 → P3 → C x⃗` rather
    than `P1 ∧ P2 ∧ P3 → C x⃗`. That is not cosmetic. The chainer matches
    premises against atomic facts, so a conjunctive premise could never fire and
    the concept would be inert in exactly the experiment meant to measure
    whether it helps. Curried, the concept can genuinely participate in search.

    A definitional extension cannot add strength, so anything the enriched
    theory proves was already provable; a change in the corpus is a change in
    what the search *reaches*, not in what is true.
    """
    from ..kernel import emit

    binders = " ".join(f"({p} : {sort})" for p in params)
    args = " ".join(params)
    parts = conjuncts(body)

    chain = "".join(f"{emit.formula(p)} → " for p in parts)
    nested = "h0"
    for i in range(1, len(parts)):
        nested = f"And.intro {nested} h{i}" if i == 1 else nested
    # build the right-nested witness explicitly
    witness = f"h{len(parts) - 1}"
    for i in range(len(parts) - 2, -1, -1):
        witness = f"(And.intro h{i} {witness})"
    lam = "".join(f"fun h{i} => " for i in range(len(parts)))
    intro = f"theorem {name}_intro {binders} : {chain}{name} {args} :=\n  {lam}{witness}\n"

    elims = []
    for i, p in enumerate(parts):
        path = "h" + ".right" * i + ("" if i == len(parts) - 1 else ".left")
        elims.append(
            f"theorem {name}_elim{i} {binders} : {name} {args} → {emit.formula(p, top=True)} :=\n"
            f"  fun h => {path}\n"
        )
    return intro, elims


def rank(scored, top=12):
    """Order by compression, then by how many clusters a concept spans.

    Deliberately not a weighted sum. The ranking is a reading order for a human,
    not a verdict.
    """
    return sorted(
        scored,
        key=lambda c: (-c["scores"]["description_size_reduction"],
                       -c["scores"]["clusters_unified"]),
    )[:top]


def summarize(ranked):
    from ..patterns import antiunify as A

    lines = []
    for c in ranked:
        s = c["scores"]
        lines.append(
            f"{c['name']}({', '.join(c['params'])}) := {A.render(c['body'])}\n"
            f"    covers {s['theorems_covered']} theorems, "
            f"{s['clusters_unified']} clusters, "
            f"DL reduction {s['description_size_reduction']}"
        )
    return "\n".join(lines)


def to_json(obj):
    return json.dumps(obj, indent=1, default=str)
