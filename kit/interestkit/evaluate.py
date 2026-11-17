"""Checks any score can be put through when ground truth exists.

All take plain dicts keyed by declaration name, so they work for any scoring
rule, not just the paper's. Standard library only.
"""

import random
import re


def rank(scores, names=None):
    """Names ordered best-first. Ties keep the order of `names` (pass a shuffled
    list to break them at random rather than by listing order)."""
    names = list(scores) if names is None else list(names)
    return sorted(names, key=lambda n: scores[n], reverse=True)


def topk_enrichment(scores, flag, k=50, resamples=2000, seed=0):
    """Share of flagged items among the top k, against the share overall.

    The 95% interval resamples the top k with replacement. `enriched` and
    `depleted` mean the interval lies strictly above or below the base rate.
    """
    order = rank(scores)
    top = order[:k]
    base = sum(1 for n in scores if flag.get(n)) / len(scores)
    share = sum(1 for n in top if flag.get(n)) / len(top)
    rnd = random.Random(seed)
    boots = sorted(sum(1 for n in (rnd.choice(top) for _ in top) if flag.get(n)) / len(top)
                   for _ in range(resamples))
    lo, hi = boots[int(0.025 * resamples)], boots[int(0.975 * resamples) - 1]
    return {"k": len(top), "base_rate": base, "share": share, "ci95": (lo, hi),
            "enriched": lo > base, "depleted": hi < base}


def filter_quality(flagged, truth, negative):
    """Recall on the `truth` items, false-positive rate on `negative`, Youden's J.

    All three are collections of names. `negative` is the set the filter should
    leave alone (in the audit, statements labelled N); items in neither set,
    such as exact restatements of an axiom, count towards nothing.
    """
    negative = set(negative)
    pos = set(truth)
    tp = len(pos & set(flagged))
    fp = len(negative & set(flagged))
    recall = tp / len(pos) if pos else None
    fpr = fp / len(negative) if negative else None
    j = recall - fpr if recall is not None and fpr is not None else None
    return {"recall": recall, "fpr": fpr, "youden_j": j, "flagged": len(set(flagged))}


def _avg_ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for t in range(i, j + 1):
            out[order[t]] = (i + j) / 2
        i = j + 1
    return out


def spearman(a, b):
    """Spearman's rho over the names both dicts share, ties averaged."""
    names = sorted(set(a) & set(b))
    ra, rb = _avg_ranks([a[n] for n in names]), _avg_ranks([b[n] for n in names])
    n = len(names)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return cov / (va * vb) if va and vb else None


# --- near-duplicates -------------------------------------------------------

_HEAD = re.compile(r"^\s*∀\s*(.*?),\s*(.*)$", re.S)


def split_statement(text):
    """(binders, hypotheses, conclusion) of a Lean-style `∀ ..., H1 → ... → C`.

    Splits on top-level arrows only. Statements without a leading ∀ have no
    binders; statements without arrows have no hypotheses.
    """
    m = _HEAD.match(text)
    binders, body = (m.group(1), m.group(2)) if m else ("", text)
    parts, depth, cur = [], 0, []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if depth == 0 and body.startswith(" → ", i):
            parts.append("".join(cur).strip())
            cur = []
            i += 3
            continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur).strip())
    return binders.strip(), tuple(parts[:-1]), parts[-1]


def one_hypothesis_apart(a, b):
    """Same binders and conclusion; hypotheses differ by one swap, insertion or deletion."""
    ba, ha, ca = split_statement(a)
    bb, hb, cb = split_statement(b)
    if ba != bb or ca != cb or a == b:
        return False
    sa, sb = list(ha), list(hb)
    for h in list(sa):
        if h in sb:
            sa.remove(h)
            sb.remove(h)
    return (len(sa), len(sb)) in ((1, 1), (1, 0), (0, 1))


def near_duplicate_share(texts):
    """Share of `texts` that have at least one other entry one hypothesis apart."""
    texts = list(texts)
    has = [False] * len(texts)
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if one_hypothesis_apart(texts[i], texts[j]):
                has[i] = has[j] = True
    return sum(has) / len(texts) if texts else None
