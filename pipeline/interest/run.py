"""Score one corpus and compute every pre-registered statistic on it.

Reads what earlier steps froze: the corpus, its labels (checked against the
hash manifest), the tactic results and euclean's importance ranking. Writes
`runs/<run>/interest/scores.jsonl` (one row per statement), `results.json`
(H1-H5 for this corpus) and `seeds.json`.

Usage:  python -m pipeline.interest.run --run interest-<code>-p<P>-s<S>
"""

import argparse
import json
from fractions import Fraction

import numpy as np

from ..kernel import emit, theory as theory_mod
from ..kernel.theory import ROOT
from . import filters, labels as labels_mod, loop, metric, plan, stats, tactics


def load(run):
    run_dir = ROOT / "runs" / run
    summary = json.loads((run_dir / "summary.json").read_text())
    spec = json.loads((ROOT / summary["spec_path"]).read_text())
    T = theory_mod.Theory(spec)
    records = json.loads((run_dir / "corpus.json").read_text())
    frozen = plan.frozen_label_hashes()
    rows, sha = labels_mod.read_labels(run_dir / "interest" / "labels.jsonl", frozen.get(run))
    if run not in frozen:
        raise SystemExit(f"{run}: no frozen label hash in {plan.LABEL_MANIFEST}")
    tac, tac_meta = tactics.read(run_dir / "interest" / "tactics.json")
    imp = {r["id"]: r["importance"] for r in json.loads((run_dir / "importance.json").read_text())}
    return run_dir, summary, T, records, {r["id"]: r for r in rows}, sha, tac, tac_meta, imp


def local_difficulty(records, tac):
    term = {r["id"]: metric.term_size(r["proof_ast"]) for r in records}
    lines = {r["id"]: metric.proof_lines(r["proof_ast"]) for r in records}
    closed = {rid: bool(tac[rid].get("triv")) or bool(tac[rid].get("grind")) for rid in term}
    tacv = {rid: 1 if closed[rid] else lines[rid] for rid in term}
    return {"term": term, "loc": lines, "tac": tacv}, closed


def analyse(run, log=print):
    run_dir, summary, T, records, lab, label_sha, tac, tac_meta, imp = load(run)
    ci = plan.corpus_index(run)
    ids = [r["id"] for r in records]
    by_id = {r["id"]: r for r in records}
    n = len(ids)
    k = plan.K

    # --- difficulty, length, interestingness, utility ----------------------
    local, tac_closed = local_difficulty(records, tac)
    refs = metric.lemma_references(records)
    V = {}
    for x in plan.V_KINDS:
        for mode in plan.MODES:
            V[(x, mode)] = metric.EXPANSIONS[mode](ids, refs, local[x])

    decls = metric.declarations(T)
    voc = {rid: metric.vocabulary(by_id[rid]["statement_ast"], T.sort) for rid in ids}
    L0 = {
        s: {rid: metric.description_length(by_id[rid]["statement"], voc[rid], set(), decls, metric.MEASURES[s])
            for rid in ids}
        for s in plan.S_KINDS
    }
    users = {rid: 0 for rid in ids}
    for r in records:
        for d in set(r["proof_dependencies"]):
            if d in users:
                users[d] += 1

    I0, ranks = {}, {}
    for x, mode, s in plan.variants():
        vals = [metric.interestingness(V[(x, mode)][rid], L0[s][rid]) for rid in ids]
        I0[(x, mode, s)] = vals
        ranks[("I0", x, mode, s)] = stats.exact_ranks(vals)
    U0 = {(x, mode): [metric.utility(users[rid], V[(x, mode)][rid]) for rid in ids]
          for x in plan.V_KINDS for mode in plan.MODES}
    px, pmode, ps = plan.PRIMARY
    ranks[("U0", px, pmode)] = stats.exact_ranks(U0[(px, pmode)])
    ranks[("importance",)] = stats.exact_ranks([imp[rid] for rid in ids])
    foot = [len(lab[rid]["footprint"]) for rid in ids]
    penal = [
        metric.interestingness(V[(px, pmode)][rid], L0[ps][rid]) * (
            0 if f <= 1 else Fraction(f - 1, f))
        for rid, f in zip(ids, foot)
    ]
    ranks[("I0corr", px, pmode, ps)] = stats.exact_ranks(penal)

    flag = {rid: lab[rid]["label"] in labels_mod.RESTATEMENT for rid in ids}
    flag_fp = {rid: flag[rid] or lab[rid]["R1fp"] for rid in ids}
    base = sum(flag.values()) / n
    base_fp = sum(flag_fp.values()) / n
    counts = {t: sum(1 for rid in ids if lab[rid]["label"] == t) for t in labels_mod.TIERS}

    # --- H1: top-k enrichment ---------------------------------------------
    h1 = {"k": k, "n": n, "base_rate": base, "base_rate_R1fp": base_fp, "label_counts": counts,
          "rankings": {}}
    fl = [flag[rid] for rid in ids]
    fl_fp = [flag_fp[rid] for rid in ids]
    for j, (key, rk) in enumerate(sorted(ranks.items(), key=lambda kv: repr(kv[0]))):
        name = "/".join(key)
        sh = stats.topk_share(rk, fl, k)
        lo, hi = stats.bootstrap_topk(rk, fl, k, (ci, 1, j))
        sh_fp = stats.topk_share(rk, fl_fp, k)
        h1["rankings"][name] = {"share": sh, "ci": [lo, hi], "share_R1fp": sh_fp,
                                "excess": sh - base}
    log(f"  H1 done ({len(ranks)} rankings)")

    # --- H2: filters ------------------------------------------------------
    texts = {rid: by_id[rid]["statement"] for rid in ids}
    for a in T.axiom_names:
        texts[a] = emit.formula(T.env[a], top=True)
    lib = filters.library(records, T.axiom_names)
    stmts = dict(T.env)
    stmts.update({rid: by_id[rid]["statement_ast"] for rid in ids})

    sim = {}
    for tok in filters.TOKENIZERS:
        sim[("lib", tok)] = [filters.max_similarity(texts[rid], [texts[p] for p in lib[rid]],
                                                    filters.TOKENIZERS[tok]) for rid in ids]
    sim[("direct", "unigram")] = [
        filters.max_similarity(texts[rid], [texts[p] for p in sorted(loop.direct_premises(by_id[rid]))])
        for rid in ids
    ]
    relevant = [
        filters.relevant(texts[rid], by_id[rid]["statement_ast"], [texts[p] for p in lib[rid]],
                         metric.premise_vocabulary([stmts[p] for p in lib[rid]], T.sort), T.sort)
        for rid in ids
    ]
    triv = [tac[rid].get("triv") is True for rid in ids]
    triv_plus = [triv[i] or tac[ids[i]].get("grind0") is True for i in range(n)]
    tac_incomplete = sum(1 for rid in ids for v in tac[rid].values() if v is None)

    lab_of = [lab[rid]["label"] for rid in ids]

    def evaluate(flagged, j):
        flagged = list(flagged)
        out = {}
        for group in ("R0", "R1", "R2"):
            idx = [i for i in range(n) if lab_of[i] == group]
            out[f"recall_{group}"] = stats.wilson(sum(flagged[i] for i in idx), len(idx))
        idx = [i for i in range(n) if lab_of[i] in ("R1", "R2")]
        out["recall_R1R2"] = stats.wilson(sum(flagged[i] for i in idx), len(idx))
        idx = [i for i in range(n) if fl[i]]
        out["recall_R"] = stats.wilson(sum(flagged[i] for i in idx), len(idx))
        idx = [i for i in range(n) if not fl[i]]
        out["fpr_N"] = stats.wilson(sum(flagged[i] for i in idx), len(idx))
        out["specificity_N"] = None if out["fpr_N"][0] is None else 1 - out["fpr_N"][0]
        nf = sum(flagged)
        out["flagged"] = nf
        out["precision"] = stats.wilson(sum(1 for i in range(n) if flagged[i] and fl[i]), nf)
        positive = [lab_of[i] in ("R1", "R2") for i in range(n)]
        keep = [i for i in range(n) if lab_of[i] != "R0"]
        out["youden_R1R2"] = stats.bootstrap_youden([flagged[i] for i in keep],
                                                    [positive[i] for i in keep], (ci, 2, j))
        return out

    h2 = {"filters": {}, "relevance_failures": n - sum(relevant), "tactic_incomplete": tac_incomplete,
          "tactic_meta": tac_meta}
    tau = filters.THRESHOLD
    rest = [s >= tau for s in sim[("lib", "unigram")]]
    h2["filters"]["triviality"] = evaluate(triv, 0)
    h2["filters"]["triviality_plus_grind"] = evaluate(triv_plus, 1)
    h2["filters"]["restatement"] = evaluate(rest, 2)
    h2["filters"]["combined"] = evaluate([a or b or not c for a, b, c in zip(triv, rest, relevant)], 3)
    h2["filters"]["restatement_bigram"] = evaluate([s >= tau for s in sim[("lib", "bigram")]], 4)
    h2["filters"]["restatement_direct"] = evaluate([s >= tau for s in sim[("direct", "unigram")]], 5)
    h2["sweep"] = {}
    for j, t in enumerate(filters.SWEEP):
        e = evaluate([s >= t for s in sim[("lib", "unigram")]], 10 + j)
        h2["sweep"][f"{t:.2f}"] = {key: e[key] for key in ("recall_R1R2", "recall_R", "fpr_N", "flagged", "youden_R1R2")}
    log("  H2 done")

    # --- H3: correlations -------------------------------------------------
    h3 = {}
    imp_vals = [imp[rid] for rid in ids]
    for j, (x, mode, s) in enumerate(plan.variants()):
        rk = ranks[("I0", x, mode, s)]
        u = U0[(x, mode)]
        keep = [i for i in range(n) if u[i] > 0]
        urk = stats.exact_ranks([u[i] for i in keep])
        name = f"{x}/{mode}/{s}"
        h3[name] = {
            "I0_U0": stats.spearman_ci(rk[keep], urk, (ci, 3, j)),
            "I0_importance": stats.spearman_ci(rk, imp_vals, (ci, 4, j)),
            "I0_footprint": stats.spearman_ci(rk, foot, (ci, 5, j)),
            "I0_users": stats.spearman_ci(rk[keep], [users[ids[i]] for i in keep], (ci, 6, j)),
        }
    log("  H3 done")

    # --- H4: growth loop --------------------------------------------------
    trivial_ids = {rid for rid, t in zip(ids, triv) if t}
    h4 = {"rounds": loop.ROUNDS, "promote": loop.PROMOTE, "policies": {}}

    def record_policy(name, history):
        prom = loop.promoted_ids(history)
        h4["policies"][name] = {
            "share": loop.share(prom, flag),
            "share_R1fp": loop.share(prom, flag_fp),
            "promoted": len(prom),
            "history": history,
        }

    for x in plan.V_KINDS:
        for s in plan.S_KINDS:
            fn = loop.interestingness_score(local[x], s, decls, T.sort, stmts)
            record_policy(f"interestingness/{x}/{s}",
                          loop.run(records, T.axiom_names, fn, trivial_ids, tie_seed=(ci, 7)))
        record_policy(f"proof_size/{x}",
                      loop.run(records, T.axiom_names, lambda r, P, x=x: local[x][r["id"]],
                               trivial_ids, tie_seed=(ci, 7)))
    record_policy("importance", loop.run(records, T.axiom_names, lambda r, P: imp[r["id"]],
                                         trivial_ids, tie_seed=(ci, 7)))
    record_policy("retain_all", loop.run(records, T.axiom_names, None, trivial_ids))

    def restated(r, P):
        return filters.max_similarity(r["statement"], [texts[p] for p in P]) >= tau

    fn = loop.interestingness_score(local[px], ps, decls, T.sort, stmts)
    record_policy(f"interestingness/{px}/{ps}+restatement_filter",
                  loop.run(records, T.axiom_names, fn, trivial_ids, tie_seed=(ci, 7),
                           restatement_filter=restated))
    h4["random"] = loop.summarise_random(records, T.axiom_names, trivial_ids, flag)
    log("  H4 done")

    # --- H5: exploratory corrected score ------------------------------------
    keep = [i for i in range(n) if U0[(px, pmode)][i] > 0]
    rk = ranks[("I0corr", px, pmode, ps)]
    h5 = {
        "topk": h1["rankings"]["/".join(("I0corr", px, pmode, ps))],
        "I0corr_U0": stats.spearman_ci(rk[keep], stats.exact_ranks([U0[(px, pmode)][i] for i in keep]),
                                       (ci, 8, 0)),
    }

    # --- write ------------------------------------------------------------
    out_dir = run_dir / "interest"
    with (out_dir / "scores.jsonl").open("w") as fh:
        for i, rid in enumerate(ids):
            row = {
                "id": rid,
                "label": lab[rid]["label"],
                "S_raw": metric.s_raw(texts[rid]),
                "S_canon": metric.s_canon(texts[rid]),
                "L0_raw": L0["raw"][rid],
                "L0_canon": L0["canon"][rid],
                "direct_users": users[rid],
                "footprint": foot[i],
                "importance": imp[rid],
                "trivial": triv[i],
                "trivial_plus_grind": triv_plus[i],
                "tactic_closed": tac_closed[rid],
                "relevant": relevant[i],
                "restatement_similarity": sim[("lib", "unigram")][i],
            }
            for x in plan.V_KINDS:
                row[f"V_{x}_local"] = local[x][rid]
                for mode in plan.MODES:
                    v = V[(x, mode)][rid]
                    row[f"V_{x}_{mode}"] = str(v)
                    row[f"log10_V_{x}_{mode}"] = metric.log10_int(v)
            for x, mode, s in plan.variants():
                row[f"log10_I0_{x}_{mode}_{s}"] = metric.log10_fraction(I0[(x, mode, s)][i])
            # App. C.1.2's order: relevance first, then restatement and triviality
            row["reward_primary"] = (
                metric.PENALTY_IRRELEVANT if not relevant[i]
                else metric.REWARD_TRIVIAL if (rest[i] or triv[i])
                else metric.reward(V[(px, pmode)][rid], L0[ps][rid])
            )
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    results = {"run": run, "corpus_index": ci, "theory": summary["theory"], "perm": summary["perm"],
               "seed": summary["chainer_seed"], "labels_sha256": label_sha,
               "H1": h1, "H2": h2, "H3": h3, "H4": h4, "H5": h5}
    (out_dir / "results.json").write_text(json.dumps(results, indent=1, sort_keys=True, default=_jsonable) + "\n")
    (out_dir / "seeds.json").write_text(json.dumps(plan.seed_record(run), indent=1) + "\n")
    log(f"wrote {out_dir}")
    return results


def _jsonable(o):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    raise TypeError(type(o))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    args = ap.parse_args()
    analyse(args.run)


if __name__ == "__main__":
    main()
