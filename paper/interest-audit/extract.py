"""Every number in the write-up, read from the frozen audit report.

Nothing here computes a result: it parses the tables that
pipeline.interest.audit generated into docs/interest-audit.md, takes ranges
over permutations and seeds, and writes them out as TeX macros and as the
executive summary. A number that is not in the report cannot appear here.
"""
import hashlib, json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
REPORT = ROOT / "docs" / "interest-audit.md"
text = REPORT.read_text()

def sections(t):
    out, cur = {}, None
    for l in t.splitlines():
        if l.startswith("## "):
            cur = l[3:].strip(); out[cur] = []
        elif cur:
            out[cur].append(l)
    return out

def tables(rows_in):
    """All markdown tables in a block, each as a list of dict rows."""
    res, cur = [], []
    for l in rows_in + [""]:
        if l.startswith("|"):
            cur.append([c.strip() for c in l.strip("|").split("|")])
        elif cur:
            hdr, rows = cur[0], [r for r in cur[2:]]
            res.append([dict(zip(hdr, r)) for r in rows]); cur = []
    return res

S = sections(text)
def sec(prefix): return next(v for k, v in S.items() if k.startswith(prefix))
def num(s): return float(re.match(r"\s*(-?[0-9.]+)", s.replace("%", "")).group(1))
def theory(run): return "subject" if "t0f85211" in run else "control"
def runid(cell): return cell.strip("`")

corp = tables(sec("Corpora"))[0]
H1 = tables(sec("H1"))
H2 = tables(sec("H2"))[0]
H3 = tables(sec("H3"))[0]
H4 = tables(sec("H4"))[0]
verdicts = tables(sec("Verdicts"))[0]

M = {}
class R:
    """A range over permutations and seeds, formatted per output.

    `fmt` is a plain format for the magnitude ("{:.2f}"); `pct` marks a
    percentage. The sign and the percent sign are added per output.
    """
    def __init__(self, vals, fmt):
        self.pct = fmt.endswith("%")
        self.fmt = fmt.rstrip("%").replace("\\", "")
        self.lo, self.hi = min(vals), max(vals)
    def _one(self, v, tex):
        body = self.fmt.format(abs(v)) + (("\\%" if tex else "%") if self.pct else "")
        return (("$-$" if tex else "\u2212") if v < 0 else "") + body
    def _fmt(self, tex):
        a = self._one(self.lo, tex)
        return a if self.lo == self.hi else f"{a} to {self._one(self.hi, tex)}"
    def tex(self): return self._fmt(True)
    def md(self): return self._fmt(False)
def rng(vals, fmt): return R(vals, fmt)

for th in ("subject", "control"):
    rows = [r for r in corp if r["theory"] == th]
    M[f"{th}Corpora"] = str(len(rows))
    M[f"{th}Kept"] = rng([int(r["kept"]) for r in rows], "{}")
    for lab, name in (("R0", "RZero"), ("R1", "ROne"), ("R2", "RTwo")):
        M[f"{th}{name}"] = rng([int(r[lab]) for r in rows], "{}")
    M[f"{th}ClockStops"] = str(sum(r["clock-stopped generations"].replace("none", "").strip(" /") != "" for r in rows))
    h1 = [r for r in H1[0] if theory(runid(r["run"])) == th]
    M[f"{th}BaseRate"] = rng([num(r["base rate"]) for r in h1], "{:.1f}\\%")
    M[f"{th}TopKShare"] = rng([num(r["top-k share, primary I0"]) for r in h1], "{:.1f}\\%")
    M[f"{th}ImpShare"] = rng([num(r["euclean importance"]) for r in h1], "{:.1f}\\%")
    h3 = [r for r in H3 if theory(runid(r["run"])) == th]
    for col, key in (("I0-U0 (n)", "RhoU"), ("I0-importance", "RhoImp"), ("I0-footprint size", "RhoFoot"), ("I0-direct users", "RhoUsers")):
        M[f"{th}{key}"] = rng([num(r[col]) for r in h3], "{:.2f}")
    h4 = [r for r in H4 if theory(runid(r["run"])) == th]
    M[f"{th}RandLo"] = rng([num(r["random band"].split("-")[0]) for r in h4], "{:.1f}\\%")
    M[f"{th}RandHi"] = rng([num(r["random band"].split("-")[1]) for r in h4], "{:.1f}\\%")
    M[f"{th}LoopI"] = rng([num(r["`interestingness/loc/raw`"]) for r in h4], "{:.1f}\\%")
    M[f"{th}LoopFilt"] = rng([num(r["`interestingness/loc/raw+restatement_filter`"]) for r in h4], "{:.1f}\\%")
    M[f"{th}LoopSize"] = rng([num(r["`proof_size/loc`"]) for r in h4], "{:.1f}\\%")
    def place(r, col):
        lo, hi = (num(x) for x in r["random band"].split("-"))
        v = num(r[col]); return "above" if v > hi else "below" if v < lo else "within"
    for col, key in (("`interestingness/loc/raw`", "LoopI"), ("`interestingness/loc/raw+restatement_filter`", "LoopFilt")):
        pl = [place(r, col) for r in h4]
        for w in ("above", "below", "within"):
            M[f"{th}{key}{w.capitalize()}"] = str(pl.count(w))
    M[f"{th}Runs"] = str(len(h4))
    col = "`interestingness/loc/raw+restatement_filter`"
    prom = [r for t in tables(sec("H4"))[1:] if t and "run" in t[0] and col in t[0] and "random band" not in t[0]
            for r in t if theory(runid(r["run"])) == th]
    if prom:
        M[f"{th}FiltPromoted"] = rng([num(r["`interestingness/loc/raw+restatement_filter`"]) for r in prom], "{:.0f}")

# H2, subject only (the control has no R1/R2 to recall)
def h2(filt, col, fmt):
    v = [num(r[col]) for r in H2 if r["filter"] == filt and theory(runid(r["run"])) == "subject"]
    return rng(v, fmt)
for filt, key in (("triviality", "Triv"), ("restatement", "Rest"), ("combined", "Comb")):
    M[f"hTwo{key}RecallOne"] = h2(filt, "recall R1", "{:.0f}\\%")
    M[f"hTwo{key}RecallTwo"] = h2(filt, "recall R2", "{:.0f}\\%")
    M[f"hTwo{key}FPR"] = h2(filt, "FPR on N", "{:.1f}\\%")
    M[f"hTwo{key}J"] = h2(filt, "J", "{:.3f}")

# H1: how many of the 8 I0 rankings are ever enriched
h1sum = H1[-1]
M["hOneVariants"] = str(sum(r["ranking"].startswith("`I0/") for r in h1sum))
M["hOneRankings"] = str(len(h1sum))
M["hOneEnrichedAny"] = str(sum(not (r["subject"].startswith("0 enriched") and r["control"].startswith("0 enriched")) for r in h1sum))

# provenance
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
M["reportSha"] = sha(REPORT)[:16]
M["preregSha"] = sha(ROOT / "docs" / "interest-prereg.md")[:16]
M["branchHead"] = git("log", "-1", "--format=%h", "--", "docs/interest-audit.md")  # last commit to touch the frozen report
M["dupIdentical"] = "byte-identical" if "byte-identical" in text else "NOT identical"
M["verdictRows"] = str(len(verdicts))

# Near-duplicates: post hoc, from kit/examples/near_duplicates.py, not the frozen report.
nd_path = OUT / "near_duplicates.json"
if nd_path.exists():
    nd = json.loads(nd_path.read_text())
    import statistics
    M["nearDupK"] = str(nd["k"])
    M["nearDupDraws"] = str(nd["draws"])
    for th in ("subject", "control"):
        rs = [r for r in nd["corpora"] if r["role"] == th]
        for key, name in (("I0", "IZero"), ("U0", "UZero"), ("importance", "Imp"), ("random_mean", "Rand")):
            M[f"{th}NearDup{name}"] = rng([100 * r[key] for r in rs], "{:.0f}%")
            M[f"{th}NearDup{name}Median"] = rng([100 * statistics.median(r[key] for r in rs)], "{:.0f}%")
        M[f"{th}NearDupAboveRandom"] = str(sum(r["I0"] > r["random_mean"] for r in rs))

OUT.mkdir(parents=True, exist_ok=True)
tex = {k: (v.tex() if isinstance(v, R) else v) for k, v in M.items()}
md = {k: (v.md() if isinstance(v, R) else v) for k, v in M.items()}
(OUT / "numbers.tex").write_text("% generated by extract.py from docs/interest-audit.md; do not edit\n" +
    "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in tex.items()))
tpl = OUT / "summary_template.md"
if tpl.exists():
    (OUT / "EXECUTIVE_SUMMARY.md").write_text(tpl.read_text().format_map(md))
print(json.dumps(md, indent=1, ensure_ascii=False))
