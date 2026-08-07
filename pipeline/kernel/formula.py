"""Formulas and terms for the anonymous theory.

Deliberately dumb: dictionaries matching the JSON in theory/spec.json, plus the
handful of operations the proof calculus needs. Nothing here knows or can know
what the relations mean.

n-ary conjunction and disjunction are right-nested to binary on load, so that
the internal shape matches how Lean parses `A ∧ B ∧ C`. Everything downstream
can then assume binary.
"""

# --- constructors ---------------------------------------------------------


def Var(name):
    return {"kind": "var", "name": name}


def Const(name):
    return {"kind": "const", "name": name}


def Atom(rel, args):
    return {"kind": "atom", "rel": rel, "args": list(args)}


def Eq(a, b):
    return {"kind": "eq", "lhs": a, "rhs": b}


def Not(f):
    return {"kind": "not", "arg": f}


def Imp(a, b):
    return {"kind": "imp", "lhs": a, "rhs": b}


def And(a, b):
    return {"kind": "and", "lhs": a, "rhs": b}


def Or(a, b):
    return {"kind": "or", "lhs": a, "rhs": b}


def Forall(vars_, body):
    return {"kind": "forall", "vars": list(vars_), "body": body} if vars_ else body


def Exists(vars_, body):
    return {"kind": "exists", "vars": list(vars_), "body": body} if vars_ else body


BINARY = ("imp", "and", "or")
QUANT = ("forall", "exists")


def normalize(f):
    """Right-nest n-ary and/or; accept both the JSON `args` form and binary."""
    k = f["kind"]
    if k in ("var", "const"):
        return dict(f)
    if k == "atom":
        return Atom(f["rel"], [normalize(a) for a in f["args"]])
    if k == "eq":
        return Eq(normalize(f["lhs"]), normalize(f["rhs"]))
    if k == "not":
        return Not(normalize(f["arg"]))
    if k in ("and", "or"):
        if "args" in f:
            parts = [normalize(a) for a in f["args"]]
            out = parts[-1]
            for p in reversed(parts[:-1]):
                out = {"kind": k, "lhs": p, "rhs": out}
            return out
        return {"kind": k, "lhs": normalize(f["lhs"]), "rhs": normalize(f["rhs"])}
    if k == "imp":
        return Imp(normalize(f["lhs"]), normalize(f["rhs"]))
    if k in QUANT:
        return {"kind": k, "vars": list(f["vars"]), "body": normalize(f["body"])}
    raise ValueError(f"unknown node kind {k!r}")


# --- inspection -----------------------------------------------------------


def key(f):
    """A hashable canonical tuple. Structural identity, not logical equality."""
    k = f["kind"]
    if k in ("var", "const"):
        return (k, f["name"])
    if k == "atom":
        return (k, f["rel"]) + tuple(key(a) for a in f["args"])
    if k == "eq":
        return (k, key(f["lhs"]), key(f["rhs"]))
    if k == "not":
        return (k, key(f["arg"]))
    if k in BINARY:
        return (k, key(f["lhs"]), key(f["rhs"]))
    if k in QUANT:
        return (k, tuple(f["vars"]), key(f["body"]))
    raise ValueError(k)


def same(a, b):
    return key(a) == key(b)


def _collect(f, kind, out):
    k = f["kind"]
    if k in ("var", "const"):
        if k == kind:
            out.add(f["name"])
        return out
    if k == "atom":
        for a in f["args"]:
            _collect(a, kind, out)
        return out
    if k == "eq":
        return _collect(f["rhs"], kind, _collect(f["lhs"], kind, out))
    if k == "not":
        return _collect(f["arg"], kind, out)
    if k in BINARY:
        return _collect(f["rhs"], kind, _collect(f["lhs"], kind, out))
    if k in QUANT:
        inner = _collect(f["body"], kind, set())
        if kind == "var":
            inner -= set(f["vars"])
        out |= inner
        return out
    raise ValueError(k)


def free_vars(f):
    return _collect(f, "var", set())


def all_var_names(f):
    """Every variable name occurring anywhere, bound or free. Used to pick
    binder names that cannot shadow something already inside the body."""
    out = set()

    def go(g):
        k = g["kind"]
        if k == "var":
            out.add(g["name"])
        elif k == "const":
            pass
        elif k == "atom":
            for a in g["args"]:
                go(a)
        elif k == "eq":
            go(g["lhs"])
            go(g["rhs"])
        elif k == "not":
            go(g["arg"])
        elif k in BINARY:
            go(g["lhs"])
            go(g["rhs"])
        elif k in QUANT:
            out.update(g["vars"])
            go(g["body"])
        else:
            raise ValueError(k)

    go(f)
    return out


def constants(f):
    return _collect(f, "const", set())


def relations(f):
    """Multiset of relation symbols, as a sorted list of (rel, count)."""
    counts = {}

    def go(g):
        k = g["kind"]
        if k == "atom":
            counts[g["rel"]] = counts.get(g["rel"], 0) + 1
            return
        if k in ("var", "const"):
            return
        if k == "eq":
            counts["="] = counts.get("=", 0) + 1
            go(g["lhs"])
            go(g["rhs"])
            return
        if k == "not":
            go(g["arg"])
            return
        if k in BINARY:
            go(g["lhs"])
            go(g["rhs"])
            return
        if k in QUANT:
            go(g["body"])
            return
        raise ValueError(k)

    go(f)
    return counts


def size(f):
    k = f["kind"]
    if k in ("var", "const"):
        return 1
    if k == "atom":
        return 1 + sum(size(a) for a in f["args"])
    if k == "eq":
        return 1 + size(f["lhs"]) + size(f["rhs"])
    if k == "not":
        return 1 + size(f["arg"])
    if k in BINARY:
        return 1 + size(f["lhs"]) + size(f["rhs"])
    if k in QUANT:
        return 1 + len(f["vars"]) + size(f["body"])
    raise ValueError(k)


# --- substitution ---------------------------------------------------------

_fresh_counter = [0]


def fresh(prefix="w"):
    _fresh_counter[0] += 1
    return f"{prefix}{_fresh_counter[0]}"


def subst(f, mapping):
    """Capture-avoiding substitution of free variables by terms."""
    if not mapping:
        return f
    k = f["kind"]
    if k == "var":
        return dict(mapping[f["name"]]) if f["name"] in mapping else dict(f)
    if k == "const":
        return dict(f)
    if k == "atom":
        return Atom(f["rel"], [subst(a, mapping) for a in f["args"]])
    if k == "eq":
        return Eq(subst(f["lhs"], mapping), subst(f["rhs"], mapping))
    if k == "not":
        return Not(subst(f["arg"], mapping))
    if k in BINARY:
        return {"kind": k, "lhs": subst(f["lhs"], mapping), "rhs": subst(f["rhs"], mapping)}
    if k in QUANT:
        active = {v: t for v, t in mapping.items() if v not in f["vars"]}
        if not active:
            return {"kind": k, "vars": list(f["vars"]), "body": f["body"]}
        incoming = set()
        for t in active.values():
            incoming |= _collect(t, "var", set())
        renames, new_vars = {}, []
        for v in f["vars"]:
            if v in incoming:
                nv = fresh("q")
                renames[v] = Var(nv)
                new_vars.append(nv)
            else:
                new_vars.append(v)
        body = subst(f["body"], renames) if renames else f["body"]
        return {"kind": k, "vars": new_vars, "body": subst(body, active)}
    raise ValueError(k)


def subst_consts(f, mapping):
    """Replace constants by terms. Constants are never bound, so no capture."""
    if not mapping:
        return f
    k = f["kind"]
    if k == "const":
        return dict(mapping[f["name"]]) if f["name"] in mapping else dict(f)
    if k == "var":
        return dict(f)
    if k == "atom":
        return Atom(f["rel"], [subst_consts(a, mapping) for a in f["args"]])
    if k == "eq":
        return Eq(subst_consts(f["lhs"], mapping), subst_consts(f["rhs"], mapping))
    if k == "not":
        return Not(subst_consts(f["arg"], mapping))
    if k in BINARY:
        return {
            "kind": k,
            "lhs": subst_consts(f["lhs"], mapping),
            "rhs": subst_consts(f["rhs"], mapping),
        }
    if k in QUANT:
        return {"kind": k, "vars": list(f["vars"]), "body": subst_consts(f["body"], mapping)}
    raise ValueError(k)


def instantiate(f, terms):
    """Strip the leading ∀ block, instantiating its binders with `terms`."""
    assert f["kind"] == "forall", f"not a ∀-formula: {f['kind']}"
    vars_ = f["vars"]
    assert len(terms) == len(vars_), f"expected {len(vars_)} args, got {len(terms)}"
    return subst(f["body"], dict(zip(vars_, terms)))


def open_exists(f, const_names):
    """Strip the leading ∃ block, replacing its binders with fresh constants."""
    assert f["kind"] == "exists", f"not an ∃-formula: {f['kind']}"
    vars_ = f["vars"]
    assert len(const_names) == len(vars_)
    return subst(f["body"], {v: Const(c) for v, c in zip(vars_, const_names)})


def premises(f):
    """Split ∀-free implication chain P1 → ... → Pk → Q into ([Pi], Q)."""
    ps = []
    while f["kind"] == "imp":
        ps.append(f["lhs"])
        f = f["rhs"]
    return ps, f
