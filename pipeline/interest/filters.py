"""The paper's relevance, restatement and triviality filters (App. C.1.2).

Patel et al. (arXiv:2609.28603), App. C.1.2: a proposal must share at least one
non-generic identifier with the premise/definition context (else -0.25);
"direct premise restatements (as measured by token-level similarity) are marked
trivial"; and a candidate closed by assumption, rfl, simp, tauto or simp_all
receives 0.

The paper gives neither the similarity measure nor its threshold. The stand-in,
fixed in the pre-registration: token-set Jaccard similarity to each premise,
threshold 0.70 (the value the paper itself uses for token-set Jaccard in
App. C.2.1, for a different purpose), with a sweep reported as secondary.

Triviality needs Lean and lives in `tactics`; this module only reads its result.
"""

import re

from ..kernel import formula as F

# Lean lexical tokens of an emitted statement: identifiers, numerals, and every
# other non-space character on its own.
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*|[0-9]+|\S")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*")

THRESHOLD = 0.70
SWEEP = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.00)


def tokens(text):
    return TOKEN.findall(text)


def unigrams(text):
    return frozenset(tokens(text))


def bigrams(text):
    t = tokens(text)
    return frozenset(zip(t, t[1:]))


TOKENIZERS = {"unigram": unigrams, "bigram": bigrams}


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def max_similarity(text, premise_texts, tokenizer=unigrams):
    """Largest token-set Jaccard similarity to any premise; 0.0 with none."""
    mine = tokenizer(text)
    best = 0.0
    for p in premise_texts:
        s = jaccard(mine, tokenizer(p))
        if s > best:
            best = s
            if best == 1.0:
                break
    return best


def bound_names(stmt):
    """Every variable name a statement binds, at any depth."""
    out = set()

    def go(f):
        k = f["kind"]
        if k in F.QUANT:
            out.update(f["vars"])
            go(f["body"])
        elif k == "not":
            go(f["arg"])
        elif k in F.BINARY:
            go(f["lhs"])
            go(f["rhs"])

    go(stmt)
    return out


def relevant(text, stmt, context_texts, context_names, sort):
    """At least one non-generic identifier shared with the context.

    Generic: the sort, and the statement's own bound variables. What is left in
    this setting is the relation symbols, so every statement that mentions a
    relation used by its premises passes. The count of failures is reported
    even when it is zero.
    """
    mine = set(IDENT.findall(text)) - {sort} - bound_names(stmt)
    ctx = set(context_names)
    for c in context_texts:
        ctx |= set(IDENT.findall(c))
    return bool(mine & ctx)


# --- the premise library a statement was generated against ----------------


def promoted_by_generation(records, promote_max=60):
    """What `chainer.run.build` folded into the rule set after each generation.

    Replicates its rule exactly: the first `promote_max` universally quantified
    statements of each generation, in record order.
    """
    by_gen = {}
    for r in records:
        by_gen.setdefault(r["generation"], []).append(r)
    out = {}
    for g, rs in by_gen.items():
        out[g] = [r["id"] for r in rs if r["statement_ast"]["kind"] == "forall"][:promote_max]
    return out


def library(records, axiom_names, promote_max=60):
    """id -> the premise set its generation could cite: axioms plus everything
    promoted in earlier generations."""
    promoted = promoted_by_generation(records, promote_max)
    gens = sorted(promoted)
    lib_at = {}
    acc = list(axiom_names)
    for g in gens:
        lib_at[g] = tuple(acc)
        acc = acc + promoted[g]
    return {r["id"]: lib_at[r["generation"]] for r in records}
