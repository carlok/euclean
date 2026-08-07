"""Propose statements the corpus does not contain, from structure it does.

Three sources, none of which consults anything semantic.

**Symmetry.** `views/symmetry.py` reports which permutations of a theorem's
binders leave it unchanged. Applying one of those is a no-op and proves nothing.
Applying a permutation it reports is *not* a symmetry produces a genuinely
different statement, and whether that statement is provable is an open question
worth asking. This source doubles as a check on the symmetry view itself: a
permutation reported as a symmetry must reproduce a known theorem, and if one
ever fails to, the view is wrong.

**Schema completion.** An anti-unified schema covers a family. Filling its holes
with a combination absent from the corpus asks whether the family has a member
nobody derived.

**Hypothesis dropping.** Remove a premise from a verified theorem. Either the
premise was doing no work, or the result is false. Both are informative, and the
second is the more common.

Nothing here decides truth. Everything proposed goes to `test.py`, and failures
are kept — a confidently proposed conjecture that turns out unprovable is data
about the proposer.
"""

import itertools

from ..canon import normalize as N
from ..kernel import formula as F
from ..patterns import antiunify as A
from ..views import symmetry


def _permuted(stmt, perm):
    vars_ = stmt["vars"]
    mapping = {vars_[i]: F.Var(vars_[perm[i]]) for i in range(len(vars_))}
    return F.Forall(vars_, F.subst(stmt["body"], mapping))


def from_symmetry(record, known, limit=6):
    """Permutations the symmetry view says are *not* symmetries.

    Also emits, as `symmetry-control`, one permutation the view says *is* a
    symmetry. That one must reproduce a known theorem; if it does not, the
    symmetry view is broken and the whole view is suspect.
    """
    stmt = record["statement_ast"]
    if stmt["kind"] != "forall" or len(stmt["vars"]) < 2:
        return []
    n = len(stmt["vars"])
    real = {tuple(sorted(p)) for p in symmetry.variable_transpositions(stmt)}

    out = []
    for i, j in itertools.combinations(range(min(n, 5)), 2):
        perm = list(range(n))
        perm[i], perm[j] = perm[j], perm[i]
        candidate = _permuted(stmt, perm)
        key = N.key(candidate)
        is_symmetry = (i, j) in real
        if is_symmetry:
            # Checked structurally, not by re-derivation. A permutation the view
            # calls a symmetry must canonicalize back to the original statement,
            # and that is a deterministic fact about the view. Routing it through
            # the bounded prover instead would only re-measure the prover's
            # recall and would report a weak prover as a broken view.
            out.append(
                {
                    "source": "symmetry-control",
                    "statement_ast": candidate,
                    "origin": record["id"],
                    "note": f"swap({i},{j}) reported as a symmetry",
                    "structurally_identical": key == N.key(stmt),
                    "structural_check": True,
                }
            )
        elif key not in known:
            out.append(
                {
                    "source": "symmetry",
                    "statement_ast": candidate,
                    "origin": record["id"],
                    "note": f"swap({i},{j}) reported as not a symmetry",
                    "expect_known": False,
                }
            )
        if len(out) >= limit:
            break
    return out


def from_hypothesis_dropping(record, known, limit=3):
    """Drop one premise. Either it was idle, or the result is false."""
    stmt = record["statement_ast"]
    body = stmt["body"] if stmt["kind"] == "forall" else stmt
    premises, concl = F.premises(body)
    if not premises:
        return []
    out = []
    for i in range(min(len(premises), limit)):
        reduced = premises[:i] + premises[i + 1 :]
        inner = concl
        for p in reversed(reduced):
            inner = F.Imp(p, inner)
        candidate = F.Forall(stmt["vars"], inner) if stmt["kind"] == "forall" else inner
        candidate = N.canonical(candidate)
        if N.key(candidate) in known:
            continue
        out.append(
            {
                "source": "hypothesis-dropping",
                "statement_ast": candidate,
                "origin": record["id"],
                "note": f"premise {i} removed",
                "expect_known": False,
            }
        )
    return out


def from_schema(schema_entry, records, known, limit=4):
    """Fill a schema's holes with variable choices the corpus never used."""
    schema = schema_entry.get("schema_ast")
    if schema is None:
        return []
    holes = sorted(A.pattern_vars(schema))
    if not holes or len(holes) > 3:
        return []

    binders = schema["vars"] if schema["kind"] == "forall" else []
    if not binders:
        return []

    out = []
    for combo in itertools.product(binders, repeat=len(holes)):
        filled = _fill(schema, dict(zip(holes, combo)))
        try:
            candidate = N.canonical(filled)
        except Exception:
            continue
        if N.key(candidate) in known:
            continue
        out.append(
            {
                "source": "schema-completion",
                "statement_ast": candidate,
                "origin": f"cluster{schema_entry.get('cluster')}",
                "note": f"holes {holes} filled with {list(combo)}",
                "expect_known": False,
            }
        )
        if len(out) >= limit:
            break
    return out


def _fill(schema, binding):
    k = schema["kind"]
    if k == "pvar":
        return F.Var(binding[schema["name"]])
    if k in ("var", "const"):
        return dict(schema)
    if k == "atom":
        return F.Atom(schema["rel"], [_fill(a, binding) for a in schema["args"]])
    if k == "eq":
        return F.Eq(_fill(schema["lhs"], binding), _fill(schema["rhs"], binding))
    if k == "not":
        return F.Not(_fill(schema["arg"], binding))
    if k in F.BINARY:
        return {"kind": k, "lhs": _fill(schema["lhs"], binding), "rhs": _fill(schema["rhs"], binding)}
    if k in F.QUANT:
        return {"kind": k, "vars": list(schema["vars"]), "body": _fill(schema["body"], binding)}
    raise ValueError(k)


def positive_controls(records, count=40, rng_seed=0):
    """Known theorems, fed through the same attempt as the conjectures.

    Without these the yield number is uninterpretable. A source scoring 0% could
    mean its conjectures are false, or it could mean the bounded attempt cannot
    reach anything at all — and those demand opposite conclusions. Statements
    already proved put a ceiling on what any yield can be, and the ceiling has
    to be reported next to the yield.
    """
    import random

    rng = random.Random(rng_seed)
    pool = [r for r in records if "∃" not in r["normalized_statement"]] or records
    picks = rng.sample(pool, min(count, len(pool)))
    return [
        {
            "source": "positive-control",
            "statement_ast": r["statement_ast"],
            "origin": r["id"],
            "note": "already proved; measures what the attempt budget can recover",
            "expect_known": True,
        }
        for r in picks
    ]


def propose(records, importance=None, schemas=(), per_source=40):
    """Gather conjectures from every source, deduplicated against the corpus."""
    known = {N.key(r["statement_ast"]) for r in records}
    by_id = {r["id"]: r for r in records}

    order = (
        [by_id[i["id"]] for i in importance if i["id"] in by_id]
        if importance
        else sorted(records, key=lambda r: r["proof_size"])
    )

    out, seen = [], set()

    def take(items, cap):
        n = 0
        for c in items:
            key = N.key(c["statement_ast"])
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
            n += 1
            if n >= cap:
                return

    # Symmetry controls are rare — only a couple of the most important theorems
    # have any variable symmetry at all — so they get their own pass. Sharing a
    # per-record cap with the ordinary symmetry conjectures crowded every one of
    # them out, and the check they provide then silently did not happen.
    for r in order:
        take([c for c in from_symmetry(r, known) if c["source"] == "symmetry-control"], 2)
        if sum(1 for c in out if c["source"] == "symmetry-control") >= 12:
            break

    for r in order[:200]:
        take([c for c in from_symmetry(r, known) if c["source"] == "symmetry"], 2)
        if sum(1 for c in out if c["source"] == "symmetry") >= per_source:
            break
    for r in order[:200]:
        take(from_hypothesis_dropping(r, known), 2)
        if sum(1 for c in out if c["source"] == "hypothesis-dropping") >= per_source:
            break
    for s in schemas:
        take(from_schema(s, records, known), 2)
        if sum(1 for c in out if c["source"] == "schema-completion") >= per_source:
            break

    out.extend(positive_controls(records, count=min(per_source, 40)))
    return out
