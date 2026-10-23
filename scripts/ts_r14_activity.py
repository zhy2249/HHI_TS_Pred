#!/usr/bin/env python3
"""Extract R14 final-Writer activity and separate RDOQ trials (no BD-rate).

Example: python3 scripts/ts_r14_activity.py runs/job/encoder.log --output-dir runs/r14_activity
Inputs are read-only. Unknown schemas, concatenated runs and duplicate inputs fail.
"""
import argparse
from collections import defaultdict
import csv
from pathlib import Path

REVISION = "R14-NF-168-v3"
NUMBERING = "compact-15-v1"
MODES = {1: 2, 2: 4, 3: 2, 4: 4, 5: 2, 6: 4, 7: 2, 8: 4,
         9: 4, 10: 2, 11: 4, 12: 2, 13: 4, 14: 2, 15: 4}
KEYS = ("mode", "component", "width", "height", "cu_qp", "intra", "bdpcm", "target",
        "cg_count_in_tu", "cutoff", "n", "state", "weight")
COUNTERS = (
    "tu_count", "cg_count", "coeff_count", "nonzero_count", "target_count", "sparse_count",
    "zero_event_count", "missing_near_count", "missing_far_count", "fixed_count",
    "eligible_count", "same_winners_count", "neutral_count", "up_count", "down_count",
    "state_change_count", "weight_change_count", "phase_only_count", "p_vs_current",
    "actual_remap_vs_current", "p_vs_initial_weight", "actual_remap_vs_initial_weight",
    "actual_remap_nonzero", "near_nonzero_sum", "far_nonzero_sum",
    "target_distance_sum", "feedback_cost_tie_count", "step_better_count", "step_worse_count",
    "step_equal_count", "next_pair_count", "next_positive_count", "next_zero_count",
    "next_negative_count", "next_gain_sum", "next_cross_cg_count", "next_phase_pair_count",
    "next_phase_gain_sum", "next_p_changed", "next_actual_remap_changed",
    "direction_reverse_count", "tu_valid_sum", "tu_first_weight_event_sum",
    "tu_with_weight", "tu_no_weight", "tu_with_pdiff", "tu_no_pdiff", "tu_remaining_valid_sum",
    "next_unpaired_count")
TRIAL_KEYS = ("mode", "component", "width", "height", "cu_qp", "intra", "cg_count_in_tu", "target")
TRIAL_COUNTERS = ("cg_trial_count", "zero_cg_count", "rolled_back_state_count")
SCHEMAS = {"stats": KEYS + COUNTERS, "trial": TRIAL_KEYS + TRIAL_COUNTERS}
LOG_SCHEMAS = {population: ("mode_n15",) + columns[1:] for population, columns in SCHEMAS.items()}
PREFIXES = {"stats": ("TS_R14_STATS_HEADER ", "TS_R14_STATS "),
            "trial": ("TS_R14_TRIAL_HEADER ", "TS_R14_TRIAL ")}
LABELS = ("numbering", "source_log", "sequence", "configuration", "nominal_qp")
GROUP = LABELS + KEYS[:9]
TRIAL_GROUP = LABELS + TRIAL_KEYS
OUTPUT_NAMES = ("final_writer.csv", "final_writer_summary.csv", "state_residence.csv",
                "rd_trial.csv", "rd_trial_summary.csv", "summary.md")


def _check(condition, message):
    if not condition:
        raise ValueError(message)


def _validate(row, population):
    _check(row["mode"] in MODES, "Unknown or retired R14 mode")
    _check(row["component"] in (0, 1, 2) and row["target"] in (0, 1)
           and row["intra"] in (0, 1), "Invalid R14 component/target/intra")
    _check(row["width"] > 0 and row["height"] > 0 and row["cg_count_in_tu"] > 0,
           "Invalid R14 geometry")
    counters = COUNTERS if population == "stats" else TRIAL_COUNTERS
    _check(all(row[k] >= 0 for k in counters if k not in ("next_gain_sum", "next_phase_gain_sum")),
           "Negative R14 count")
    if population == "trial":
        _check(row["rolled_back_state_count"] <= row["zero_cg_count"] <= row["cg_trial_count"],
               "Invalid RDOQ trial denominator")
        return
    _check(row["bdpcm"] in (0, 1, 2), "Invalid BDPCM value")
    sentinel = all(row[k] == -1 for k in ("cutoff", "n", "state", "weight"))
    if sentinel:
        _check(row["coeff_count"] == 0, "TU/CG sentinel cannot count coefficients")
    else:
        k = MODES[row["mode"]]
        cap = 2 * k + 1 if row["mode"] >= 10 else k
        _check(row["cutoff"] in (-1, 0, 2, 10) and 0 <= row["n"] <= 5
               and 0 <= row["state"] <= cap and 0 <= row["weight"] <= k,
               "Invalid R14 state/support/cutoff")
        _check(row["tu_count"] == 0 and row["cg_count"] == 0,
               "TU/CG totals must use sentinel rows")
        _check(row["weight"] == (row["state"] // 2 if row["mode"] >= 10 else row["state"]),
               "R14 state/output weight mismatch")
        if row["mode"] in (7, 8, 9):
            _check(row["weight"] == {7: 0, 8: 1, 9: 3}[row["mode"]],
                   "Fixed R14 weight changed")
    coeff, eligible, pairs = row["coeff_count"], row["eligible_count"], row["next_pair_count"]
    _check(row["nonzero_count"] + row["zero_event_count"] == coeff, "Coefficient zero/nonzero partition")
    _check(eligible <= row["nonzero_count"] and row["target_count"] <= coeff,
           "Invalid coefficient/eligible denominator")
    _check(row["up_count"] + row["down_count"] + row["neutral_count"] == eligible,
           "Feedback direction partition")
    _check(row["state_change_count"] == row["weight_change_count"] + row["phase_only_count"] <= eligible,
           "State/weight/phase partition")
    _check(row["step_better_count"] + row["step_worse_count"] + row["step_equal_count"] == eligible,
           "Immediate feedback partition")
    _check(row["next_positive_count"] + row["next_zero_count"] + row["next_negative_count"] == pairs,
           "g_next sign partition")
    _check(row["next_phase_pair_count"] <= pairs <= eligible
           and row["next_cross_cg_count"] <= pairs, "g_next pair denominator")
    _check(row["next_phase_gain_sum"] == 0, "Phase-only g_next must be zero")
    _check(row["next_phase_pair_count"] <= row["next_zero_count"], "Phase-only pairs must have zero gain")
    _check(row["actual_remap_vs_current"] <= row["actual_remap_nonzero"] <= row["nonzero_count"],
           "Actual remapping denominator")
    _check(row["p_vs_current"] <= coeff and row["same_winners_count"] <= eligible
           and row["feedback_cost_tie_count"] <= eligible, "Invalid activity denominator")
    _check(row["p_vs_initial_weight"] <= coeff
           and row["actual_remap_vs_initial_weight"] <= row["actual_remap_nonzero"]
           and row["next_actual_remap_changed"] <= row["next_p_changed"] <= pairs,
           "Invalid learning-specific activity denominator")
    if row["n"] < 3 or row["mode"] in (7, 8, 9):
        _check(eligible == 0, "Sparse/fixed R14 cannot learn")
    if not row["target"] or row["bdpcm"]:
        _check(not any(row[k] for k in ("eligible_count", "p_vs_current", "actual_remap_vs_current",
                                        "p_vs_initial_weight", "actual_remap_vs_initial_weight")),
               "Non-target path has R14 activity")
    if row["cutoff"] <= 0:
        _check(not any(row[k] for k in ("actual_remap_nonzero", "actual_remap_vs_current",
                                        "actual_remap_vs_initial_weight", "next_actual_remap_changed")),
               "Pure bypass/zero CG has actual remapping")


def parse(text):
    """Return {'stats': [...], 'trial': [...]}; never combine the populations.

    Empty population lists mean no report, not an observed count of zero.
    One header per population is allowed; concatenated logs must be split.
    """
    headers, rows, seen = {}, {"stats": [], "trial": []}, {"stats": set(), "trial": set()}
    for line_number, line in enumerate(text.splitlines(), 1):
        for population, (header_prefix, row_prefix) in PREFIXES.items():
            if line.startswith(header_prefix):
                columns = tuple(line[len(header_prefix):].split(","))
                _check(population not in headers,
                       f"Multiple R14 {population} reports in one log: split runs before extraction")
                _check(len(set(columns)) == len(columns) and columns == LOG_SCHEMAS[population],
                       f"Incompatible R14 {population} header at line {line_number}; compact-15-v1 requires mode_n15 (do not reinterpret old numbering)")
                headers[population] = SCHEMAS[population]
            elif line.startswith(row_prefix):
                _check(population in headers, f"R14 {population} row before header")
                fields = line[len(row_prefix):].split(",")
                _check(len(fields) == len(headers[population]),
                       f"Truncated or incompatible R14 {population} row at line {line_number}")
                try:
                    row = dict(zip(headers[population], map(int, fields)))
                except ValueError as exc:
                    raise ValueError(f"Noninteger R14 {population} value at line {line_number}") from exc
                _validate(row, population)
                keys = KEYS if population == "stats" else TRIAL_KEYS
                identity = tuple(row[k] for k in keys)
                _check(identity not in seen[population], f"Duplicate R14 {population} key in one log")
                seen[population].add(identity)
                rows[population].append(row)
    # Aggregate conservation is checked separately for each mode/geometry/target.
    for row in aggregate(rows["stats"], KEYS[:9], COUNTERS):
        _check(row["tu_with_weight"] + row["tu_no_weight"] == row["tu_count"], "Incomplete R14 TU weight totals")
        _check(row["tu_with_pdiff"] + row["tu_no_pdiff"] == row["tu_count"], "Incomplete R14 TU predictor totals")
        _check(row["tu_valid_sum"] == row["eligible_count"], "Incomplete R14 TU eligible totals")
        _check(row["next_pair_count"] + row["next_unpaired_count"] == row["eligible_count"],
               "Incomplete R14 g_next pairing (unpaired TU tails must be retained)")
    return rows


def ratio(num, den):
    return num / den if den else ""


def aggregate(rows, keys, counters):
    totals = defaultdict(lambda: dict.fromkeys(counters, 0))
    for row in rows:
        for field in counters:
            totals[tuple(row[k] for k in keys)][field] += row[field]
    return [dict(zip(keys, key), **value) for key, value in sorted(totals.items())]


def final_metrics(row):
    eligible, pairs, tu = row["eligible_count"], row["next_pair_count"], row["tu_count"]
    return {
        "eligible_fraction_coeff": ratio(eligible, row["coeff_count"]),
        "predictor_difference_fraction_target": ratio(row["p_vs_current"], row["target_count"]),
        "actual_remap_difference_fraction_regular_nonzero": ratio(row["actual_remap_vs_current"], row["actual_remap_nonzero"]),
        "predictor_vs_initial_fraction_target": ratio(row["p_vs_initial_weight"], row["target_count"]),
        "actual_remap_vs_initial_fraction_regular_nonzero": ratio(row["actual_remap_vs_initial_weight"], row["actual_remap_nonzero"]),
        "state_change_fraction_eligible": ratio(row["state_change_count"], eligible),
        "weight_change_fraction_eligible": ratio(row["weight_change_count"], eligible),
        "phase_only_fraction_eligible": ratio(row["phase_only_count"], eligible),
        "same_winners_fraction_eligible": ratio(row["same_winners_count"], eligible),
        "feedback_tie_fraction_eligible": ratio(row["feedback_cost_tie_count"], eligible),
        "mean_target_distance": ratio(row["target_distance_sum"], eligible),
        "mean_next_gain": ratio(row["next_gain_sum"], pairs),
        "next_positive_fraction": ratio(row["next_positive_count"], pairs),
        "next_zero_fraction": ratio(row["next_zero_count"], pairs),
        "next_negative_fraction": ratio(row["next_negative_count"], pairs),
        "next_cross_cg_fraction": ratio(row["next_cross_cg_count"], pairs),
        "next_phase_pair_fraction": ratio(row["next_phase_pair_count"], pairs),
        "next_p_changed_fraction": ratio(row["next_p_changed"], pairs),
        "next_actual_remap_changed_fraction": ratio(row["next_actual_remap_changed"], pairs),
        "mean_next_phase_gain": ratio(row["next_phase_gain_sum"], row["next_phase_pair_count"]),
        "mean_next_nonphase_gain": ratio(row["next_gain_sum"] - row["next_phase_gain_sum"],
                                           pairs - row["next_phase_pair_count"]),
        "tu_weight_change_fraction": ratio(row["tu_with_weight"], tu),
        "tu_predictor_difference_fraction": ratio(row["tu_with_pdiff"], tu),
        "mean_eligible_per_tu": ratio(row["tu_valid_sum"], tu),
        "mean_first_weight_event_changed_tu": ratio(row["tu_first_weight_event_sum"], row["tu_with_weight"]),
        "mean_remaining_eligible_changed_tu": ratio(row["tu_remaining_valid_sum"], row["tu_with_weight"]),
    }


def trial_metrics(row):
    return {"zero_cg_fraction_trials": ratio(row["zero_cg_count"], row["cg_trial_count"]),
            "rollback_fraction_zero_trials": ratio(row["rolled_back_state_count"], row["zero_cg_count"]),
            "rollback_fraction_all_trials": ratio(row["rolled_back_state_count"], row["cg_trial_count"])}


def _csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _display(value, percent=False):
    if value == "":
        return "—"
    return f"{100 * value:.3f}%" if percent else f"{value:.6g}"


def _markdown(stats, trials, inputs):
    lines = [f"# R14 activity extraction ({REVISION}, numbering={NUMBERING})", "", f"Source logs: {len(inputs)}.", "",
             "Final Writer and RDOQ trials are separate populations. Ratios below use sums of counts, "
             "not averages of log percentages. Missing denominators are shown as —.", "",
             "`g_next` is the next eligible coefficient's fixed-q integer syntax-cost difference; "
             "positive favors the previous weight update. It is neither measured CABAC bits nor BD-rate. "
             "Final TS selection and the active quantization trajectory still condition this observation.", "",
             "## Final Writer", ""]
    if not stats:
        lines += ["No final-Writer report was found; no final coding activity is inferred from trial counts.", ""]
    else:
        lines += ["| Mode | Target | TU | Coeff | Eligible | Weight-change TU | Mapping changes vs Current / initial (regular NZ denominator) | g_next pairs | Mean g_next | Positive / zero / negative | Phase-only pairs |",
                  "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |"]
        for row in aggregate(stats, ("mode", "target"), COUNTERS):
            m = final_metrics(row)
            signs = " / ".join(_display(m[f"next_{x}_fraction"], True) for x in ("positive", "zero", "negative"))
            lines.append(f"| {row['mode']} | {row['target']} | {row['tu_count']} | {row['coeff_count']} | {row['eligible_count']} | "
                         f"{_display(m['tu_weight_change_fraction'], True)} | {row['actual_remap_vs_current']} / {row['actual_remap_vs_initial_weight']} (N={row['actual_remap_nonzero']}) | "
                         f"{row['next_pair_count']} | {_display(m['mean_next_gain'])} | {signs} | {row['next_phase_pair_count']} |")
        lines += ["", "`target=0` is kept separate. g_next excludes the unpaired final eligible event of each TU; "
                  "those tails are retained in `next_unpaired_count`. Phase-only pairs must have zero gain. "
                  "Nonphase pairs can still include neutral updates.", "",
                  "`final_writer_summary.csv` retains source, component, dimensions, CU QP, intra/inter and target groups. "
                  "`state_residence.csv` counts the state/weight on entry to each coefficient, including zero and bypass positions; "
                  "its fractions use coefficients of the same source/group as denominator. Sentinel TU/CG rows are excluded.", ""]
        lines += ["`p_vs_current` and `actual_remap_vs_current` compare with native Current. "
                  "`p_vs_initial_weight` and `actual_remap_vs_initial_weight` compare the current adaptive weight "
                  "with this mode's initial weight on the same local H. `next_p_changed` and "
                  "`next_actual_remap_changed` isolate the preceding update's action on the next eligible position. "
                  "These learning-specific comparisons are not interchangeable with differences from Current.", ""]
    lines += ["## RDOQ trials", ""]
    if not trials:
        lines += ["No RDOQ trial report was found; absence is not a measured zero rollback rate.", ""]
    else:
        lines += ["| Mode | Target | CG trials | Zero-CG trials | State rollbacks | Zero / trials | Rollback / zero trials |",
                  "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for row in aggregate(trials, ("mode", "target"), TRIAL_COUNTERS):
            m = trial_metrics(row)
            lines.append(f"| {row['mode']} | {row['target']} | {row['cg_trial_count']} | {row['zero_cg_count']} | "
                         f"{row['rolled_back_state_count']} | {_display(m['zero_cg_fraction_trials'], True)} | "
                         f"{_display(m['rollback_fraction_zero_trials'], True)} |")
        lines += ["", "These are search trials, including discarded candidates; they cannot be used as the final-Writer denominator. "
                  "No RD gain or future-position benefit is inferred from the rollback count.", ""]
    lines += ["## Sources", "", *[f"- `{str(path).replace('`', '')}`" for path in inputs], "",
              "Sequence/configuration/nominal-QP labels are caller supplied; the script does not infer them from filenames. "
              "Actual CU QP remains a separate field.", ""]
    return "\n".join(lines)


def export(inputs, output_dir, sequence="", configuration="", nominal_qp=""):
    inputs = [Path(p) for p in inputs]
    output_dir = Path(output_dir)
    _check(bool(inputs), "No input logs supplied")
    resolved = [p.resolve() for p in inputs]
    _check(len(set(resolved)) == len(resolved), "Duplicate input log would double-count activity")
    _check(not set(resolved) & {(output_dir / name).resolve() for name in OUTPUT_NAMES},
           "Activity output must not overwrite an input log")
    stats, trials = [], []
    # Validate every input before writing any output file.
    for path in inputs:
        parsed = parse(path.read_text(encoding="utf-8", errors="replace"))
        _check(bool(parsed["stats"] or parsed["trial"]),
               f"{path}: no R14 statistics; observation defaults OFF (TS_R14_STATS=1 required)")
        labels = dict(numbering=NUMBERING, source_log=str(path), sequence=sequence, configuration=configuration, nominal_qp=nominal_qp)
        stats.extend(dict(labels, **row) for row in parsed["stats"])
        trials.extend(dict(labels, **row) for row in parsed["trial"])
    final_summary = [dict(row, **final_metrics(row)) for row in aggregate(stats, GROUP, COUNTERS)]
    trial_summary = [dict(row, **trial_metrics(row)) for row in aggregate(trials, TRIAL_GROUP, TRIAL_COUNTERS)]
    totals = {tuple(row[k] for k in GROUP): row["coeff_count"] for row in final_summary}
    residence = aggregate([row for row in stats if row["state"] >= 0], GROUP + ("state", "weight"),
                          ("coeff_count", "eligible_count"))
    for row in residence:
        row["far_weight_fraction"] = row["weight"] / MODES[row["mode"]]
        row["coeff_fraction"] = ratio(row["coeff_count"], totals[tuple(row[k] for k in GROUP)])
    output_dir.mkdir(parents=True, exist_ok=True)
    _csv(output_dir / "final_writer.csv", LABELS + SCHEMAS["stats"], stats)
    _csv(output_dir / "rd_trial.csv", LABELS + SCHEMAS["trial"], trials)
    metric_keys = tuple(final_metrics(dict.fromkeys(COUNTERS, 0)))
    _csv(output_dir / "final_writer_summary.csv", GROUP + COUNTERS + metric_keys, final_summary)
    _csv(output_dir / "rd_trial_summary.csv", TRIAL_GROUP + TRIAL_COUNTERS + tuple(trial_metrics(dict.fromkeys(TRIAL_COUNTERS, 0))), trial_summary)
    _csv(output_dir / "state_residence.csv", GROUP + ("state", "weight", "coeff_count", "eligible_count",
                                                      "far_weight_fraction", "coeff_fraction"), residence)
    (output_dir / "summary.md").write_text(_markdown(stats, trials, inputs), encoding="utf-8")
    return {"final_writer_rows": len(stats), "trial_rows": len(trials),
            "final_groups": len(final_summary), "trial_groups": len(trial_summary)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sequence", default="", help="Optional caller label; never inferred")
    parser.add_argument("--configuration", default="")
    parser.add_argument("--nominal-qp", default="", help="Optional job QP; cu_qp is retained separately")
    args = parser.parse_args()
    try:
        counts = export(args.logs, args.output_dir, args.sequence, args.configuration, args.nominal_qp)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"R14 final-Writer rows={counts['final_writer_rows']}, RDOQ-trial rows={counts['trial_rows']} -> {args.output_dir}; populations kept separate")


if __name__ == "__main__":
    main()
