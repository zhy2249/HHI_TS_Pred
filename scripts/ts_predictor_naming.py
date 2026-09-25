"""Result directory labels use public experiment macro numbers, not policy IDs.

Keep runtime mode names stable. Register future numbered rounds here explicitly;
do not infer macro numbers from an alphabetically sorted list.
"""
from pathlib import Path

R4_MODE_NUMBERS = {
    'r4_identity_only': 1,
    'r4_magnitude_only': 2,
    'r4_guard_rescue': 3,
    'r4_directional_risk': 4,
    'r4_causal_models': 5,
    'r4_signed_plane': 6,
}
R5_MODE_NUMBERS = {'r5_margin_first': 1, 'r5_current_veto': 2}
R6_MODE_NUMBERS = {
    'r6_dense_nopred': 1, 'r6_reject_nopred': 2,
    'r6_trim_cost': 3, 'r6_trim_saving': 4,
    'r6_sparse_max': 5, 'r6_sparse_mean': 6, 'r6_sparse_min': 7,
}
R7_MODE_NUMBERS = {'rate_raw': 1, 'rate_guard': 2}  # Stable pre-rename runtime names.
R8_MODE_NUMBERS = {
    'r8_raw_sparse_max': 1, 'r8_guard_sparse_max': 4, 'r8_reject_nopred': 8,
    'r8_mixed_raw': 13, 'r8_complete_raw': 15, 'r8_complete_sparse_max': 16,
    'r8_minimax': 17, 'r8_smoothed_dense': 19,
}


def directory_name(mode: str) -> str:
    if mode in R8_MODE_NUMBERS:
        return f'r8_{R8_MODE_NUMBERS[mode]}_{mode.removeprefix("r8_")}'
    if mode in R7_MODE_NUMBERS:
        return f'r7_{R7_MODE_NUMBERS[mode]}_{mode.removeprefix("rate_")}'
    if mode in R6_MODE_NUMBERS:
        return f'r6_{R6_MODE_NUMBERS[mode]}_{mode.removeprefix("r6_")}'
    if mode in R5_MODE_NUMBERS:
        return f'r5_{R5_MODE_NUMBERS[mode]}_{mode.removeprefix("r5_")}'
    if mode in R4_MODE_NUMBERS:
        return f'r4_{R4_MODE_NUMBERS[mode]}_{mode.removeprefix("r4_")}'
    return mode  # Preserve pre-R4 layouts.


def experiment_directory(root: Path, mode: str) -> Path:
    """Use public round numbers; retain old RATE and unnumbered resume paths."""
    canonical = root / directory_name(mode)
    candidates = [canonical]
    if mode in R7_MODE_NUMBERS:
        candidates.append(root / f'rate_{R7_MODE_NUMBERS[mode]}_{mode.removeprefix("rate_")}')
    if root / mode not in candidates:
        candidates.append(root / mode)
    existing = [p for p in candidates if p.exists()]
    if len(existing) > 1:
        raise ValueError('Ambiguous experiment directories: '+', '.join(map(str,existing))+
                         '; reconcile them before running or analysing')
    if existing:
        return existing[0]
    return canonical
