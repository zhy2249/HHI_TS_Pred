#!/usr/bin/env python3
"""Audit one fixed-q, common-entry-context R13 TS syntax replay.

Scores ending in 168 are the KeepHit surrogate, never CABAC bits. Bin costs
are CABAC fractional units (32768 per bit). Matching a syntax event permits
accounting, but does not independently isolate symbol and context causation.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

SCALE = 32768
BRANCHES = ("current", "eq", "sp")
SLOTS = ("L", "U", "D", "LL", "UU")
TEXT_FIELDS = {"branch", "kind", "syntax"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_csv(path):
    with path.open(newline="") as stream:
        return [{k: v if k in TEXT_FIELDS else (int(v) if v else None)
                 for k, v in row.items()} for row in csv.DictReader(stream)]


def write_csv(path, rows, fields=None):
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def syntax_cost(m, rice, span):
    if m < 2:
        return m
    cost = 2 + sum(m >= limit for limit in (2, 4, 6, 8))
    if m < 10:
        return cost
    value, cutoff = (m - 10) // 2, 5
    if value < cutoff * (1 << rice):
        return cost + (value >> rice) + 1 + rice
    cap, code = 32 - cutoff - span, (value >> rice) - cutoff
    if code >= (1 << cap) - 1:
        return cost + cutoff + cap + span
    prefix = 0
    while code > (2 << prefix) - 2:
        prefix += 1
    return cost + cutoff + 2 * prefix + rice + 1


def loss168(m, p, rice, span):
    cost = lambda a: syntax_cost(a, rice, span)
    if p <= 1:
        return 168 * cost(m)
    if p == m:
        return 168
    if p == m - 1:
        c = min(cost(m), 22)
        return 168 * c - 4 * (c - 1) ** 2
    if p == m + 1:
        c = cost(m + 1)
        return 168 * c - 4 * (c - 1) ** 2 if c <= 11 else 84 * c + 525
    return 168 * cost(m + (p > m))


def predict(h, branch, rice, span):
    current = max(h[:2])
    n = sum(a != 0 for a in h)
    weights = [2 if branch == "sp" and j < 2 else 1 for j in range(5)]
    weight_sum = sum(w for a, w in zip(h, weights) if a)
    if branch == "current" or n < 3:
        return current, [], [], n, weight_sum
    canonical = current if current > 1 else 0
    candidates = [canonical] + ([0] if canonical else [])
    candidates += sorted(set(a for a in h if a > 1 and a != canonical))
    scores = [sum(w * loss168(a, p, rice, span) for a, w in zip(h, weights) if a)
              for p in candidates]
    winner = min(range(len(scores)), key=scores.__getitem__)
    return candidates[winner], candidates, scores, n, weight_sum


def remap(a, p):
    return 0 if not a else 1 if a == p else a + 1 if a < p else a


def pair_bins(bins, coefficients):
    keyed, visits, event_numbers = {}, Counter(), Counter()
    for row in bins:
        row = dict(row, event_index=event_numbers[row["branch"]])
        event_numbers[row["branch"]] += 1
        base = tuple(row[k] for k in ("cg", "scan", "pass", "syntax"))
        visit_key = (row["branch"],) + base
        occurrence = visits[visit_key]
        visits[visit_key] += 1
        keyed.setdefault(base + (occurrence,), {})[row["branch"]] = row
    output = []
    syntax_order = {name: i for i, name in enumerate(("sig_group", "sig", "sign", "gt1", "parity", "gt2", "gt4", "gt6", "gt8", "remainder", "sign_ep"))}
    order = lambda item: (item[0][0], item[0][2], item[0][1], syntax_order[item[0][3]], item[0][4])
    for key, branches in sorted(keyed.items(), key=order):
        if not {"eq", "sp"}.intersection(branches):
            continue
        eq, sp = branches.get("eq"), branches.get("sp")
        context_changed = None
        symbol_changed = None
        if eq is None:
            category = "syntax_only_in_sp"
        elif sp is None:
            category = "syntax_only_in_eq"
        else:
            symbol_changed = eq["value"] != sp["value"]
            context_changed = any(eq[f] != sp[f] for f in
                                  ("ctx_id", "state0", "state1", "frac0", "frac1"))
            if symbol_changed:
                category = "symbol_and_context_changed" if context_changed else "symbol_changed_context_same"
            elif context_changed:
                category = "same_symbol_context_changed"
            elif eq["bypass_length"] != sp["bypass_length"]:
                category = "same_symbol_bypass_length_changed"
            else:
                category = "unchanged"
                require(eq["cost_frac"] == sp["cost_frac"], "Unexplained cost change with equal symbol/context")
        row = dict(zip(("cg", "scan", "pass", "syntax", "occurrence"), key))
        row.update(category=category, symbol_changed=symbol_changed, context_changed=context_changed)
        scan = key[1]
        for branch, source in (("eq", eq), ("sp", sp)):
            for field in ("event_index", "value", "ctx_id", "state0", "state1", "frac0", "frac1", "regular_budget_before", "bypass_length"):
                row[branch + "_" + field] = source[field] if source else None
            row[branch + "_cost_frac"] = source["cost_frac"] if source else 0
            row[branch + "_predictor"] = coefficients[(scan, branch)]["predictor"] if scan >= 0 else None
        row["sp_minus_eq_frac"] = row["sp_cost_frac"] - row["eq_cost_frac"]
        row["sp_minus_eq_bits"] = row["sp_minus_eq_frac"] / SCALE
        output.append(row)
    return output


def write_trace_tables(path, process, paired, result):
    """Human-readable trace tables; experimental interpretation belongs in the report."""
    text = ["# 单 TU predictor 与 syntax 追踪", "",
            "本表固定同一份 q 和同一个 TS residual 入口 CABAC context。Current 是同输入反事实分支，不能当作独立 anchor 编码。",
            "评分为 KeepHit 整数×168，不是 bit；`cost_frac/32768` 才是 CABAC 估计 bit。坐标为 TU 内位置。", "",
            f"SP−EQ = {result['sp_minus_eq_frac']} / 32768 = {result['sp_minus_eq_bits']:.12f} bit。", "",
            "## 全部非零 coefficient", "",
            "`p→ã` 表示 predictor 与 regular remapping；实际 level 和 regular 是否启用保留在 CSV。", "",
            "| Scan | (x,y) | q | L,U,D,LL,UU | n | Current p→ã | EQ p→ã | SP p→ã | SP−EQ 估计 bit |",
            "|---:|:---:|---:|:---:|---:|:---:|:---:|:---:|---:|"]
    for row in process:
        if row["q"]:
            fields = [str(row["scan"]), f"({row['x']},{row['y']})", str(row["q"]),
                      ",".join(str(row[s]) for s in SLOTS), str(row["n"])]
            fields += [f"{row[b+'_predictor']}→{row[b+'_regular_remap']}" for b in BRANCHES]
            fields += [f"{row['sp_minus_eq_bits']:+.12f}"]
            text.append("| " + " | ".join(fields) + " |")
    text += ["", "## 全部有评分的位置", "",
             "候选 `p:score168` 按代码测试顺序列出；仅严格降低才更新，平局保留顺序靠前候选。`n<3` 未评分，直接 Current。", "",
             "| Scan | q | L,U,D,LL,UU | EQ 候选/分数 | EQ winner | SP 候选/分数 | SP winner | 平局 EQ/SP |",
             "|---:|---:|:---:|:---|---:|:---|---:|:---:|"]
    for row in process:
        if row["eq_scored"]:
            fields = [str(row["scan"]), str(row["q"]), ",".join(str(row[s]) for s in SLOTS),
                      row["eq_candidate_scores168"], str(row["eq_predictor"]),
                      row["sp_candidate_scores168"], str(row["sp_predictor"]),
                      f"{row['eq_tied']}/{row['sp_tied']}"]
            text.append("| " + " | ".join(fields) + " |")
    text += ["", "## 零 coefficient 的 predictor 变化", "",
             "q=0 始终 remap 为 0，因此单独改变这些位置的 predictor 不改变其 syntax；若出现 rate 差异，应归因于前面 context/预算传播。", "",
             "| Scan | (x,y) | L,U,D,LL,UU | n | Current / EQ / SP p |",
             "|---:|:---:|:---:|---:|:---:|"]
    for row in process:
        if not row["q"] and row["predictor_changed"]:
            text.append(f"| {row['scan']} | ({row['x']},{row['y']}) | " +
                        ",".join(str(row[s]) for s in SLOTS) + f" | {row['n']} | " +
                        " / ".join(str(row[b + "_predictor"]) for b in BRANCHES) + " |")
    text += ["", "## 改变的 syntax 事件", "",
             "配对依照 CG/scan/pass/syntax/同类次数。`—` 表示该分支没有此事件。类别只作差额记账，不将 symbol 与 context 的共同变化强行拆成独立因果效应。", "",
             "| CG | Scan | Pass | Syntax | EQ value | SP value | EQ cost frac | SP cost frac | SP−EQ bit | 类别 |",
             "|---:|---:|---:|:---|---:|---:|---:|---:|---:|:---|"]
    for row in paired:
        if row["category"] != "unchanged":
            fields = [str(row[k]) for k in ("cg", "scan", "pass", "syntax")]
            fields += ["—" if row[b + "_value"] is None else str(row[b + "_value"]) for b in ("eq", "sp")]
            fields += [str(row[b + "_cost_frac"]) for b in ("eq", "sp")]
            fields += [f"{row['sp_minus_eq_bits']:+.12f}", row["category"]]
            text.append("| " + " | ".join(fields) + " |")
    text += ["", "完整 TU 的 coefficient 过程见 `coefficient_process.csv`；逐候选逐邻居贡献见 `candidate_process.csv`；完整 syntax 配对及 context state 见 `paired_bins.csv`。", ""]
    path.write_text("\n".join(text))


def analyze(prefix, output, expected_delta=90521):
    paths = {name: Path(str(prefix) + "_" + name + ".csv") for name in ("coeff", "candidates", "bins", "summary")}
    raw = {name: read_csv(path) for name, path in paths.items()}
    coefficients = {(r["scan"], r["branch"]): r for r in raw["coeff"]}
    require(len(coefficients) == len(raw["coeff"]), "Duplicate coefficient row")
    tus = {r["branch"]: r for r in raw["summary"] if r["kind"] == "TU"}
    require(set(tus) == set(BRANCHES), "Need one TU per current/EQ/SP branch")
    geometry = tus["eq"]
    count = geometry["width"] * geometry["height"]
    require(len(coefficients) == count * 3, "Incomplete coefficient grid")
    rice, span = geometry["rice"], geometry["range"]
    for branch in BRANCHES:
        require(all(tus[branch][f] == geometry[f] for f in
                    ("poc", "component", "x", "y", "width", "height", "rice", "range", "entry_budget")),
                "Branches do not describe the same TU")
    native = [r for r in tus.values() if r["validated"]]
    require(len(native) == 1 and native[0]["rate_frac"] == native[0]["native_frac"],
            "Native estimator validation absent/ambiguous")
    by_xy = {(r["x"], r["y"]): abs(r["q"]) for r in raw["coeff"] if r["branch"] == "current"}
    candidate_rows = defaultdict(list)
    for row in raw["candidates"]:
        require(row["branch"] in ("eq", "sp"), "Unexpected candidate branch")
        candidate_rows[(row["scan"], row["branch"], row["candidate_order"])].append(row)
    seen_candidate_groups = set()
    process = []
    for scan in range(count):
        base = coefficients[(scan, "current")]
        x, y = base["x"], base["y"]
        offsets = ((-1, 0), (0, -1), (-1, -1), (-2, 0), (0, -2))
        h = [by_xy.get((x + dx, y + dy), 0) for dx, dy in offsets]
        availability = sum((0 <= x + dx < geometry["width"] and 0 <= y + dy < geometry["height"]) << j
                           for j, (dx, dy) in enumerate(offsets))
        row = {k: base[k] for k in ("scan", "cg", "raster", "x", "y", "q", "abs_q", "available_mask", *SLOTS, "n")}
        row.update(global_x=geometry["x"] + x, global_y=geometry["y"] + y)
        require([base[s] for s in SLOTS] == h and base["available_mask"] == availability,
                f"Support geometry mismatch scan={scan}")
        require(base["raster"] == y * geometry["width"] + x and base["abs_q"] == abs(base["q"]), "Bad q/raster")
        for branch in BRANCHES:
            source = coefficients[(scan, branch)]
            require(all(source[f] == base[f] for f in ("q", "raster", "x", "y", *SLOTS, "n", "available_mask")), "Branch q/support differs")
            p, candidates, scores, n, weight_sum = predict(h, branch, rice, span)
            require(source["predictor"] == p and source["n"] == n and source["weight_sum"] == weight_sum,
                    f"Predictor/count mismatch scan={scan} branch={branch}")
            require(source["scored"] == bool(candidates), "Scoring flag mismatch")
            tied = bool(scores) and scores.count(min(scores)) > 1
            require(source["tied"] == tied, "Tie flag mismatch")
            require(source["regular_remap"] == remap(abs(base["q"]), p), "Remap mismatch")
            require(source["actual_coding_level"] == (source["regular_remap"] if source["regular_active"] else abs(base["q"])), "Actual level mismatch")
            for order, (candidate, score) in enumerate(zip(candidates, scores)):
                key = scan, branch, order
                seen_candidate_groups.add(key)
                entries = candidate_rows[key]
                require(len(entries) == n and sorted(e["slot"] for e in entries) == [j for j, a in enumerate(h) if a],
                        f"Missing/duplicate candidate slots {key}")
                require(sum(e["weighted_loss168"] for e in entries) == score, "Candidate sum mismatch")
                for entry in entries:
                    j = entry["slot"]
                    weight = 2 if branch == "sp" and j < 2 else 1
                    expected = {"n": n, "weight_sum": weight_sum, "candidate": candidate,
                                "selected": candidate == p, "total_score168": score,
                                "slot_magnitude": h[j], "slot_weight": weight,
                                "base_syntax_cost": syntax_cost(h[j], rice, span),
                                "raised_syntax_cost": syntax_cost(h[j] + 1, rice, span),
                                "loss168": loss168(h[j], candidate, rice, span),
                                "weighted_loss168": weight * loss168(h[j], candidate, rice, span)}
                    require(all(entry[k] == v for k, v in expected.items()), f"Candidate detail mismatch {key}, slot={j}")
            for field in ("weight_sum", "scored", "tied", "predictor", "regular_remap", "regular_active", "actual_coding_level", "cutoff", "pass1_last", "pass2_last", "pass1_frac", "pass2_frac", "bypass_frac", "total_frac"):
                row[branch + "_" + field] = source[field]
            if branch != "current":
                row[branch + "_candidate_scores168"] = ";".join(f"{p}:{s}" for p, s in zip(candidates, scores))
        row["predictor_changed"] = row["eq_predictor"] != row["sp_predictor"]
        row["regular_remap_changed"] = row["eq_regular_remap"] != row["sp_regular_remap"]
        row["actual_level_changed"] = row["eq_actual_coding_level"] != row["sp_actual_coding_level"]
        row["sp_minus_eq_frac"] = row["sp_total_frac"] - row["eq_total_frac"]
        row["sp_minus_eq_bits"] = row["sp_minus_eq_frac"] / SCALE
        process.append(row)
    require(set(candidate_rows) == seen_candidate_groups, "Unexpected candidate rows")
    # Audit cumulative order and both coefficient/CG accounting before pairing.
    totals, cg_totals, pass_totals = Counter(), Counter(), Counter()
    group_flag_totals = Counter()
    for row in raw["bins"]:
        branch = row["branch"]
        require(branch in BRANCHES, "Unknown bin branch")
        totals[branch] += row["cost_frac"]
        require(totals[branch] == row["cumulative_frac"], "Bin cumulative accounting mismatch")
        cg_totals[(branch, row["cg"])] += row["cost_frac"]
        if row["scan"] < 0:
            require(row["syntax"] == "sig_group", "Unknown non-coefficient bin")
            group_flag_totals[branch] += row["cost_frac"]
        else:
            require(row["pass"] in (1, 2, 3), "Invalid coefficient pass")
            pass_totals[(row["scan"], branch, row["pass"])] += row["cost_frac"]
        if row["ctx_id"] < 0:
            require(row["cost_frac"] == SCALE * row["bypass_length"], "Bypass length mismatch")
        else:
            require(row["value"] in (0, 1) and row["cost_frac"] == row["frac1" if row["value"] else "frac0"], "Context probability cost mismatch")
    for (scan, branch), row in coefficients.items():
        for stage, field in enumerate(("pass1_frac", "pass2_frac", "bypass_frac"), 1):
            require(row[field] == pass_totals[(scan, branch, stage)], "Coefficient pass accounting mismatch")
        require(row["total_frac"] == sum(row[f] for f in ("pass1_frac", "pass2_frac", "bypass_frac")), "Coefficient total mismatch")
    for row in raw["summary"]:
        actual = totals[row["branch"]] if row["kind"] == "TU" else cg_totals[(row["branch"], row["cg"])]
        require(row["rate_frac"] == actual, "CG/TU accounting mismatch")
    for branch in BRANCHES:
        require(sum(r["total_frac"] for r in coefficients.values() if r["branch"] == branch) + group_flag_totals[branch] == totals[branch], "Coefficient plus group flag mismatch")
    delta = totals["sp"] - totals["eq"]
    if expected_delta is not None:
        require(delta == expected_delta, f"Expected delta {expected_delta}, got {delta}")
    paired = pair_bins(raw["bins"], coefficients)
    require(sum(r["sp_minus_eq_frac"] for r in paired) == delta, "Paired bin delta mismatch")
    by_category = defaultdict(lambda: {"count": 0, "delta_frac": 0})
    by_syntax = defaultdict(lambda: {"count": 0, "delta_frac": 0})
    for row in paired:
        for group, key in ((by_category, row["category"]), (by_syntax, row["syntax"])):
            group[key]["count"] += 1
            group[key]["delta_frac"] += row["sp_minus_eq_frac"]
    for group in (by_category, by_syntax):
        for value in group.values():
            value["delta_bits"] = value["delta_frac"] / SCALE
    result = {
        "validated": True, "units": {"score168": "KeepHit surrogate times 168; not bits", "rate_frac": "CABAC fractional units; 32768 per bit"},
        "inputs": {name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in paths.items()},
        "tu": {f: geometry[f] for f in ("poc", "component", "x", "y", "width", "height", "rice", "range", "entry_budget")},
        "coefficient_count": count, "nonzero_count": sum(r["q"] != 0 for r in process),
        "abs_sum": sum(abs(r["q"]) for r in process), "native_branch": native[0]["branch"],
        "rate_frac": dict(totals), "rate_bits": {b: totals[b] / SCALE for b in BRANCHES},
        "sp_minus_eq_frac": delta, "sp_minus_eq_bits": delta / SCALE,
        "predictor_changed_scans": [r["scan"] for r in process if r["predictor_changed"]],
        "regular_remap_changed_scans": [r["scan"] for r in process if r["regular_remap_changed"]],
        "actual_level_changed_scans": [r["scan"] for r in process if r["actual_level_changed"]],
        "rate_changed_scans": [r["scan"] for r in process if r["sp_minus_eq_frac"]],
        "changed_coefficients": [r for r in process if r["predictor_changed"] or r["sp_minus_eq_frac"]],
        "bin_category_accounting": dict(by_category), "syntax_accounting": dict(by_syntax),
        "interpretation": "Fixed q and common entry context; paired bins account for observed rate changes. Symbol/context categories are descriptive, not independently isolated causal interventions. No inference about full-sequence BD-rate.",
    }
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "coefficient_process.csv", process)
    write_csv(output / "nonzero_process.csv", [r for r in process if r["q"]], list(process[0]))
    write_csv(output / "zero_predictor_changes.csv", [r for r in process if not r["q"] and r["predictor_changed"]], list(process[0]))
    write_csv(output / "candidate_process.csv", raw["candidates"], list(raw["candidates"][0]) if raw["candidates"] else ["scan", "branch"])
    write_csv(output / "paired_bins.csv", paired)
    write_csv(output / "changed_bins.csv", [r for r in paired if r["category"] != "unchanged"], list(paired[0]) if paired else [])
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    write_trace_tables(output / "trace_tables.md", process, paired, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=Path, help="Capture prefix before _coeff.csv etc.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-delta", type=int, default=90521,
                        help="Expected SP minus EQ fractional units (default: Johnny POC16 90521)")
    args = parser.parse_args()
    result = analyze(args.prefix, args.output_dir, args.expected_delta)
    print(json.dumps({k: result[k] for k in ("validated", "rate_frac", "sp_minus_eq_frac", "sp_minus_eq_bits", "predictor_changed_scans", "actual_level_changed_scans", "rate_changed_scans")}, indent=2))


if __name__ == "__main__":
    main()
