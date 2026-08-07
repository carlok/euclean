"""Syntactic, dependency, proof and behavioural views of a theorem.

Each view is computed mechanically from the statement or the proof term. None
of them consults a name, a comment, or anything an interpreter would supply —
that is the point of the exercise, so it is worth stating plainly.

The syntactic view carries a Weisfeiler-Lehman hash of the formula graph.
Variable occurrences share a node, so information flows between the positions a
variable occupies, which is what lets `R1 b0 b1 b0 b1` and `R1 b0 b1 b1 b0` come
out with different signatures. Argument position is part of the edge label, so
the hash stays sensitive to argument order — a relation's slots are not assumed
interchangeable.
"""

import hashlib
from collections import Counter

from ..canon import normalize as N
from ..kernel import formula as F


# --- syntax ---------------------------------------------------------------


def formula_graph(stmt):
    """Returns (labels, adjacency) where adjacency[i] = [(edge_label, j), ...]."""
    labels, adj = [], []
    var_node = {}

    def new(label):
        labels.append(label)
        adj.append([])
        return len(labels) - 1

    def link(a, b, label):
        adj[a].append((label, b))
        adj[b].append((f"^{label}", a))

    def var(name, kind):
        if name not in var_node:
            var_node[name] = new(f"var:{kind}")
        return var_node[name]

    def go(f, binder_of):
        k = f["kind"]
        if k == "var":
            return var(f["name"], binder_of.get(f["name"], "free"))
        if k == "const":
            return new("const")
        if k == "atom":
            n = new(f"atom:{f['rel']}")
            for i, a in enumerate(f["args"]):
                link(n, go(a, binder_of), f"arg{i}")
            return n
        if k == "eq":
            n = new("eq")
            link(n, go(f["lhs"], binder_of), "arg0")
            link(n, go(f["rhs"], binder_of), "arg1")
            return n
        if k == "not":
            n = new("not")
            link(n, go(f["arg"], binder_of), "arg0")
            return n
        if k in F.BINARY:
            n = new(k)
            link(n, go(f["lhs"], binder_of), "arg0")
            link(n, go(f["rhs"], binder_of), "arg1")
            return n
        if k in F.QUANT:
            inner = dict(binder_of)
            for v in f["vars"]:
                inner[v] = k
            n = new(k)
            link(n, go(f["body"], inner), "body")
            return n
        raise ValueError(k)

    go(stmt, {})
    return labels, adj


def wl_signature(stmt, rounds=3):
    labels, adj = formula_graph(stmt)
    cur = list(labels)
    for _ in range(rounds):
        nxt = []
        for i, lab in enumerate(cur):
            neigh = sorted(f"{e}:{cur[j]}" for e, j in adj[i])
            nxt.append(_h(lab + "|" + ",".join(neigh)))
        cur = nxt
    return _h(",".join(sorted(cur)))


def _h(s):
    return hashlib.blake2s(s.encode(), digest_size=8).hexdigest()


def syntax_features(stmt):
    canon = N.canonical(stmt)
    premises, concl = (
        F.premises(canon["body"]) if canon["kind"] == "forall" else F.premises(canon)
    )
    rels = F.relations(canon)
    binders = len(canon["vars"]) if canon["kind"] == "forall" else 0

    core = concl["body"] if concl["kind"] == "exists" else concl
    var_uses = Counter()

    def count(f):
        k = f["kind"]
        if k == "var":
            var_uses[f["name"]] += 1
        elif k == "atom":
            for a in f["args"]:
                count(a)
        elif k == "eq":
            count(f["lhs"])
            count(f["rhs"])
        elif k == "not":
            count(f["arg"])
        elif k in F.BINARY:
            count(f["lhs"])
            count(f["rhs"])
        elif k in F.QUANT:
            count(f["body"])

    count(canon)
    repeats = sum(1 for v in var_uses.values() if v > 1)

    return {
        "binders": binders,
        "premises": len(premises),
        "negated_premises": sum(1 for p in premises if p["kind"] == "not"),
        "equational_premises": sum(1 for p in premises if p["kind"] == "eq"),
        "size": F.size(canon),
        "conclusion_kind": concl["kind"],
        "conclusion_existential_vars": len(concl["vars"]) if concl["kind"] == "exists" else 0,
        "conclusion_relation": core.get("rel", core["kind"]),
        "distinct_variables": len(var_uses),
        "repeated_variables": repeats,
        "max_variable_uses": max(var_uses.values(), default=0),
        **{f"rel_{r}": c for r, c in sorted(rels.items())},
        "wl": wl_signature(canon),
    }


# --- dependency, proof, behaviour ----------------------------------------


def dependency_features(record, axiom_names):
    ax = record["axiom_dependencies"]
    lem = record["proof_dependencies"]
    return {
        "axioms_used": len(ax),
        "lemmas_used": len(lem),
        "axiom_set": frozenset(ax),
        "lemma_set": frozenset(lem),
        "dependency_set": frozenset(ax) | frozenset(lem),
        **{f"uses_{a}": int(a in ax) for a in sorted(axiom_names)},
    }


def proof_features(record):
    nodes = record["proof_nodes"]
    branching = dict(record["proof_branching"])
    total = max(sum(branching.values()), 1)
    return {
        "proof_size": record["proof_size"],
        "proof_depth": record["proof_depth"],
        "proof_leaves": branching.get(0, 0),
        "proof_leaf_ratio": branching.get(0, 0) / total,
        "proof_branch_nodes": sum(c for d, c in branching.items() if d >= 2),
        **{f"node_{k}": v for k, v in sorted(nodes.items())},
    }


def behaviour_view(records):
    """Which theorems each theorem is later used to prove.

    Reuse is the only view that cannot be computed from a theorem alone; it is a
    property of the corpus around it. It is also the closest thing available to
    an importance signal that owes nothing to interpretation.
    """
    by_id = {r["id"]: r for r in records}
    users = {r["id"]: set() for r in records}
    for r in records:
        for dep in r["proof_dependencies"]:
            if dep in users:
                users[dep].add(r["id"])

    downstream = {}
    for rid in users:
        seen, frontier = set(), list(users[rid])
        while frontier:
            n = frontier.pop()
            if n in seen:
                continue
            seen.add(n)
            frontier.extend(users.get(n, ()))
        downstream[rid] = seen

    out = {}
    for r in records:
        rid = r["id"]
        spans = [by_id[u]["generation"] for u in users[rid]]
        out[rid] = {
            "direct_uses": len(users[rid]),
            "downstream_closure": len(downstream[rid]),
            "generation_reach": (max(spans) - r["generation"]) if spans else 0,
        }
    return out
