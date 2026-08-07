"""Plotkin least-general generalization over statements.

Given a family of theorems, produce the most specific schema of which they are
all instances. Where the members agree the schema keeps the structure; where
they differ it introduces a pattern variable, and the same disagreement always
gets the same variable — that consistency is what stops the generalization
collapsing to "some formula".

A schema is only interesting if it retains structure. `specificity` reports how
much survived, and a schema near zero should be read as "this cluster has
nothing in common", which is a finding, not a failure.
"""

from ..kernel import formula as F


def PVar(name):
    return {"kind": "pvar", "name": name}


def pkey(f):
    """Structural key that tolerates pattern variables.

    The kernel's `key` deliberately knows nothing about holes, and folding an
    lgg across a family means comparing partially generalized formulas against
    concrete ones, so the comparison needs its own key.
    """
    k = f["kind"]
    if k in ("var", "const", "pvar"):
        return (k, f["name"])
    if k == "atom":
        return (k, f["rel"]) + tuple(pkey(a) for a in f["args"])
    if k == "eq":
        return (k, pkey(f["lhs"]), pkey(f["rhs"]))
    if k == "not":
        return (k, pkey(f["arg"]))
    if k in F.BINARY:
        return (k, pkey(f["lhs"]), pkey(f["rhs"]))
    if k in F.QUANT:
        return (k, tuple(f["vars"]), pkey(f["body"]))
    raise ValueError(k)


def lgg(a, b, table=None, counter=None):
    """Least general generalization of two formulas or terms."""
    table = {} if table is None else table
    counter = [0] if counter is None else counter

    def fresh(pair):
        if pair not in table:
            table[pair] = PVar(f"a{counter[0]}")
            counter[0] += 1
        return table[pair]

    def go(x, y):
        if x["kind"] != y["kind"]:
            return fresh((repr(pkey(x)), repr(pkey(y))))
        k = x["kind"]
        if k in ("var", "const"):
            if x["name"] == y["name"]:
                return dict(x)
            return fresh((f"{k}:{x['name']}", f"{k}:{y['name']}"))
        if k == "pvar":
            return dict(x) if x["name"] == y["name"] else fresh((repr(x), repr(y)))
        if k == "atom":
            if x["rel"] != y["rel"] or len(x["args"]) != len(y["args"]):
                return fresh((repr(pkey(x)), repr(pkey(y))))
            return F.Atom(x["rel"], [go(p, q) for p, q in zip(x["args"], y["args"])])
        if k == "eq":
            return F.Eq(go(x["lhs"], y["lhs"]), go(x["rhs"], y["rhs"]))
        if k == "not":
            return F.Not(go(x["arg"], y["arg"]))
        if k in F.BINARY:
            return {"kind": k, "lhs": go(x["lhs"], y["lhs"]), "rhs": go(x["rhs"], y["rhs"])}
        if k in F.QUANT:
            if len(x["vars"]) != len(y["vars"]):
                return fresh((repr(pkey(x)), repr(pkey(y))))
            return {"kind": k, "vars": list(x["vars"]), "body": go(x["body"], y["body"])}
        raise ValueError(k)

    return go(a, b), table, counter


def generalize(formulas):
    """Fold `lgg` across a family. Returns (schema, pattern_variable_count)."""
    if not formulas:
        return None, 0
    table, counter = {}, [0]
    acc = formulas[0]
    for f in formulas[1:]:
        acc, table, counter = lgg(acc, f, table, counter)
    return acc, counter[0]


def pattern_vars(schema):
    out = set()

    def go(f):
        k = f["kind"]
        if k == "pvar":
            out.add(f["name"])
        elif k == "atom":
            for a in f["args"]:
                go(a)
        elif k == "eq":
            go(f["lhs"])
            go(f["rhs"])
        elif k == "not":
            go(f["arg"])
        elif k in F.BINARY:
            go(f["lhs"])
            go(f["rhs"])
        elif k in F.QUANT:
            go(f["body"])

    go(schema)
    return out


def size(schema):
    k = schema["kind"]
    if k in ("var", "const", "pvar"):
        return 1
    if k == "atom":
        return 1 + sum(size(a) for a in schema["args"])
    if k == "eq":
        return 1 + size(schema["lhs"]) + size(schema["rhs"])
    if k == "not":
        return 1 + size(schema["arg"])
    if k in F.BINARY:
        return 1 + size(schema["lhs"]) + size(schema["rhs"])
    if k in F.QUANT:
        return 1 + len(schema["vars"]) + size(schema["body"])
    raise ValueError(k)


def specificity(schema):
    """Share of the schema that is concrete rather than a hole. 1.0 means the
    members were identical; near 0 means the generalization says nothing."""
    total = size(schema)
    holes = _count_holes(schema)
    return (total - holes) / total if total else 0.0


def _count_holes(schema):
    k = schema["kind"]
    if k == "pvar":
        return 1
    if k in ("var", "const"):
        return 0
    if k == "atom":
        return sum(_count_holes(a) for a in schema["args"])
    if k == "eq":
        return _count_holes(schema["lhs"]) + _count_holes(schema["rhs"])
    if k == "not":
        return _count_holes(schema["arg"])
    if k in F.BINARY:
        return _count_holes(schema["lhs"]) + _count_holes(schema["rhs"])
    if k in F.QUANT:
        return _count_holes(schema["body"])
    raise ValueError(k)


def instance_of(schema, formula, binding=None):
    """Is `formula` an instance of `schema`? Pattern variables bind uniformly."""
    binding = {} if binding is None else binding

    def go(s, f):
        if s["kind"] == "pvar":
            prev = binding.get(s["name"])
            if prev is not None:
                return pkey(prev) == pkey(f)
            binding[s["name"]] = f
            return True
        if s["kind"] != f["kind"]:
            return False
        k = s["kind"]
        if k in ("var", "const"):
            return s["name"] == f["name"]
        if k == "atom":
            return (
                s["rel"] == f["rel"]
                and len(s["args"]) == len(f["args"])
                and all(go(p, q) for p, q in zip(s["args"], f["args"]))
            )
        if k == "eq":
            return go(s["lhs"], f["lhs"]) and go(s["rhs"], f["rhs"])
        if k == "not":
            return go(s["arg"], f["arg"])
        if k in F.BINARY:
            return go(s["lhs"], f["lhs"]) and go(s["rhs"], f["rhs"])
        if k in F.QUANT:
            return len(s["vars"]) == len(f["vars"]) and go(s["body"], f["body"])
        return False

    return go(schema, formula)


def render(schema):
    """Display form. Pattern variables print as Greek-free placeholders so the
    output stays copy-pasteable next to real Lean."""
    k = schema["kind"]
    if k == "pvar":
        return f"?{schema['name']}"
    if k in ("var", "const"):
        return schema["name"]
    if k == "atom":
        return schema["rel"] + " " + " ".join(render(a) for a in schema["args"])
    if k == "eq":
        return f"({render(schema['lhs'])} = {render(schema['rhs'])})"
    if k == "not":
        return f"(¬ {render(schema['arg'])})"
    if k == "imp":
        return f"({render(schema['lhs'])} → {render(schema['rhs'])})"
    if k == "and":
        return f"({render(schema['lhs'])} ∧ {render(schema['rhs'])})"
    if k == "or":
        return f"({render(schema['lhs'])} ∨ {render(schema['rhs'])})"
    if k in F.QUANT:
        b = "∀" if k == "forall" else "∃"
        return f"({b} {' '.join(schema['vars'])}, {render(schema['body'])})"
    raise ValueError(k)
