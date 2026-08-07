"""Recurring shapes inside proof terms.

A proof's *head* is the axiom or lemma being applied once the modus-ponens
spine is stripped. Recording which heads feed which gives a rule-level view of
proof structure that is independent of the statements involved — two theorems
about entirely different things can still be proved the same way, and that is
exactly the kind of family the dependency and syntax views miss.
"""

from collections import Counter

from ..kernel import proof as P


def head(pf):
    """The rule at the top of an application spine, if there is one."""
    while pf["t"] in ("mp", "andL", "andR", "eqSymm"):
        pf = pf["fn"] if pf["t"] == "mp" else pf.get("p", pf.get("fn"))
    return pf["name"] if pf["t"] == "ax" else f"<{pf['t']}>"


def applications(pf):
    """Every application in the term, as (head, tuple of argument heads).

    Each application is reported once, at the outermost node of its
    modus-ponens spine. Recursing into the spine as an ordinary child would
    re-report every prefix of the same application — `f a`, then `f a b`, then
    `f a b c` — so a rule with three premises appeared three times under three
    different motif keys, all of them describing one inference. That inflated
    both the occurrence counts and the number of distinct motifs.
    """
    out = []

    def go(p):
        if p["t"] == "mp":
            spine, args = p, []
            while spine["t"] == "mp":
                args.append(spine["arg"])
                spine = spine["fn"]
            args.reverse()
            if spine["t"] == "ax":
                out.append((spine["name"], tuple(head(a) for a in args)))
            else:
                go(spine)
            for a in args:
                go(a)
            return
        for c in P.children(p):
            go(c)

    go(pf)
    return out


def motif_counts(records):
    edges, shapes = Counter(), Counter()
    per_theorem = {}
    for r in records:
        apps = applications(r["proof_ast"])
        local = set()
        for h, args in apps:
            shapes[(h, len(args))] += 1
            for a in args:
                edges[(a, h)] += 1
                local.add((a, h))
        per_theorem[r["id"]] = local
    return edges, shapes, per_theorem


def top_motifs(records, limit=25):
    edges, shapes, per_theorem = motif_counts(records)
    support = Counter()
    for _, local in per_theorem.items():
        for e in local:
            support[e] += 1
    return {
        "application_shapes": [
            {"rule": h, "arity": n, "count": c} for (h, n), c in shapes.most_common(limit)
        ],
        "feeds": [
            {"from": a, "into": b, "occurrences": edges[(a, b)], "theorems": support[(a, b)]}
            for (a, b), _ in support.most_common(limit)
        ],
    }
