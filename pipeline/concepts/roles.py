"""Concepts mined from proof roles rather than statement syntax.

The existing miner asks which hypotheses co-occur in statements. This one asks
which inference steps keep being performed together, which is closer to what a
mathematician means by a concept: not "these conditions appear side by side" but
"this move keeps getting made".

The candidate for a motif is not reconstructed by unification. The corpus
already contains, inside its proof terms, concrete instances of the motif being
applied — so a representative subterm is lifted out, its free hypotheses are
discharged as premises and its free constants generalized, and the result is a
composite lemma that arrives with a proof already attached. Lean then checks it
like anything else.

Candidates come out as lemmas, not definitions. A recurring proof pattern is a
reusable inference step, and `chainer_run.build` already knows how to promote a
lemma into the rule set. The consequence is that role and syntactic candidates
are directly comparable on search acceleration, where both enter the environment
as rules, and are *not* comparable on description size. Nothing downstream should
put them in one table on that axis.
"""

from collections import Counter, defaultdict

from ..canon import normalize as N
from ..chainer import filters
from ..chainer.engine import free_hyps
from ..kernel import formula as F, proof as P
from ..patterns import motifs


def rule_fed(motif):
    """Does this motif consume the output of another rule?

    A motif whose every argument is a bare hypothesis says only "this rule was
    applied", which is not a pattern. The composite steps worth naming are the
    ones where one rule's conclusion feeds another's premise.
    """
    return any(not a.startswith("<") for a in motif[1])


def mine(records, min_support=10, top=40):
    """Frequent rule-fed motifs, counted once per theorem.

    Per-theorem counting matters: a motif applied forty times inside one proof
    is one habit of one proof, not a pattern across the corpus, and occurrence
    counting cannot tell those apart.
    """
    support = Counter()
    holders = defaultdict(set)
    for r in records:
        for m in set(motifs.applications(r["proof_ast"])):
            if rule_fed(m):
                support[m] += 1
                holders[m].add(r["id"])
    frequent = [(m, n) for m, n in support.most_common() if n >= min_support]
    return [(m, n, sorted(holders[m])) for m, n in frequent[:top]]


def _binder_scan(pf, env, wanted, found):
    """Walk a closed proof term, tracking what is in scope, and lift out the
    first subterm realizing each wanted motif."""

    def walk(p, hyps, consts):
        t = p["t"]
        if t == "gen":
            walk(p["body"], hyps, consts + list(p["consts"]))
            return
        if t == "lam":
            walk(p["body"], {**hyps, p["hyp"]: p["prop"]}, consts)
            return
        if t == "exE":
            walk(p["src"], hyps, consts)
            src = P.infer(p["src"], env, hyps)
            opened = F.open_exists(src, p["consts"])
            walk(p["body"], {**hyps, p["hyp"]: opened}, consts + list(p["consts"]))
            return
        if t == "orE":
            walk(p["src"], hyps, consts)
            src = P.infer(p["src"], env, hyps)
            walk(p["body0"], {**hyps, p["hyp0"]: src["lhs"]}, consts)
            walk(p["body1"], {**hyps, p["hyp1"]: src["rhs"]}, consts)
            return
        if t == "mp":
            spine, args = p, []
            while spine["t"] == "mp":
                args.append(spine["arg"])
                spine = spine["fn"]
            args.reverse()
            if spine["t"] == "ax":
                key = (spine["name"], tuple(motifs.head(a) for a in args))
                if key in wanted and key not in found:
                    found[key] = (p, dict(hyps), list(consts))
            else:
                walk(spine, hyps, consts)
            for a in args:
                walk(a, hyps, consts)
            return
        for c in P.children(p):
            walk(c, hyps, consts)

    walk(pf, {}, [])


def lift(subterm, hyps, consts, env):
    """Close a proof subterm into a standalone lemma.

    Free hypotheses become premises and free constants become binders, in that
    order — the same order `Engine.extract` uses, and for the same reason: a
    constant cannot be generalized while a hypothesis still mentions it.
    """
    used = free_hyps(subterm)
    pf = subterm
    for name in sorted(used, reverse=True):
        if name in hyps:
            pf = P.Lam(name, hyps[name], pf)
    live = [c for c in consts if c in P.term_constants(pf)]
    if live:
        pf = P.Gen(live, pf)
    return P.infer(pf, env), pf


def verify(records, cands, log=None):
    """Kernel-check role lemmas in a scope where the corpus is visible.

    A lifted subterm cites the corpus lemmas its host proof cited, so checking
    it against the axioms alone fails on unknown identifiers — correctly. The
    corpus is re-emitted first and the role lemmas appended as a final
    generation, which is exactly the import chaining the corpus driver already
    performs between its own generations.
    """
    from collections import defaultdict as _dd

    from ..chainer import run as chainer_run

    by_gen = _dd(list)
    for r in records:
        by_gen[r["generation"]].append((r["id"], r["statement_ast"], r["proof_ast"]))
    items = [by_gen[g] for g in sorted(by_gen)]
    items.append([(f"role_{i:03d}", c["statement_ast"], c["proof_ast"]) for i, c in enumerate(cands)])
    return chainer_run.verify_corpus(items, log=log or (lambda *a: None))


def candidates(records, theory, min_support=10, top=40, log=None):
    """Composite lemmas for the corpus's most repeated inference steps."""
    env = dict(theory.env)
    for r in records:
        env[r["id"]] = r["statement_ast"]

    frequent = mine(records, min_support, top)
    wanted = {m for m, _, _ in frequent}
    meta = {m: (n, holders) for m, n, holders in frequent}
    by_id = {r["id"]: r for r in records}

    found = {}
    # smallest proofs first: the lifted subterm is a representative, and a
    # representative taken from a compact proof is easier to check by eye and
    # cheaper for the kernel
    for r in sorted(records, key=lambda r: r["proof_size"]):
        if len(found) == len(wanted):
            break
        try:
            _binder_scan(r["proof_ast"], env, wanted, found)
        except Exception:
            continue  # a term we cannot walk is not a candidate, not a crash

    known = {N.key(s) for s in theory.env.values()}
    known |= {N.key(r["statement_ast"]) for r in records}

    out, seen = [], set()
    for key, (subterm, hyps, consts) in found.items():
        try:
            stmt, pf = lift(subterm, hyps, consts, env)
        except Exception as exc:
            if log:
                log(f"  role candidate {key} could not be closed: {type(exc).__name__}")
            continue
        ck = N.key(stmt)
        if ck in seen or ck in known:
            continue  # already a theorem or an axiom: a restatement, not a step
        # A lifted subterm often carries side conditions the surrounding proof
        # happened to have in hand, producing a strictly weaker version of a
        # theorem already known. The corpus filters exist for exactly this and
        # apply unchanged here.
        if filters.weakening_of_known(stmt, known) or filters.irrelevant_hypothesis(stmt):
            continue
        seen.add(ck)
        support, holders = meta[key]
        body = stmt["body"] if stmt["kind"] == "forall" else stmt
        out.append(
            {
                "key": repr(ck),
                "motif": {"rule": key[0], "arguments": list(key[1])},
                "body": body,
                "params": list(stmt["vars"]) if stmt["kind"] == "forall" else [],
                "statement_ast": stmt,
                "proof_ast": pf,
                "support": support,
                "theorems": [t for t in holders if t in by_id],
                "source": "proof-role",
            }
        )
    return out
