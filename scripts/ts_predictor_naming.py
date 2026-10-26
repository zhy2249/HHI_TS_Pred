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
    'r8_raw_sparse_mean': 2, 'r8_raw_sparse_min': 3,
    'r8_guard_sparse_mean': 5, 'r8_guard_sparse_min': 6,
    'r8_dense_nopred': 7, 'r8_trim_cost': 9, 'r8_trim_saving': 10,
    'r8_reject_sparse_max': 11, 'r8_trim_sparse_max': 12,
    'r8_mixed_guard': 14, 'r8_minimax_complete': 18,
    'r8_smoothed_all_support': 20, 'r8_dual_path': 21, 'r8_causal_path': 22,
    'r8_r3_dual_quant': 23, 'r8_raw_dual_quant': 24,
}
R9_MODE_NUMBERS = dict(zip((
    'r9_p10','r9_p12','r9_axis_sparse','r9_half_penalty','r9_feature_penalty',
    'r9_unit_risk','r9_protect_one','r9_joint_mapping','r9_expert_integer',
    'r9_expert_fractional','r9_quant_down','r9_quant_down_up','r9_axis_feature'), range(1,14)))
R10_MODE_NUMBERS = dict(zip((
    'r10_expert_axis_A','r10_expert_p1_A','r10_integer_then_fractional',
    'r10_matched_state_weights','r10_delete_one_validation',
    'r10_protected_mapping_expert','r10_axis_A_tiebreak'), range(1,8)))
R11_MODE_NUMBERS = dict(zip((
    'r11_no_evidence_r3','r11_query_context_tie','r11_same_cg_local8','r11_same_tu_local8',
    'r11_add_native_current','r11_add_identity','r11_no_evidence_query','r11_no_evidence_tu8'), range(1,9)))
R12_MODE_NUMBERS = dict(zip((
    'r12_ci_near1','r12_r3_near1','r12_current_near1','r12_loo_unstable_cf','r12_direct_first',
    'r12_r3_near1_loo','r12_c_distance_raw','r12_c_distance_fulltrim','r12_validation_distance',
    'r12_validation_distance_tie','r12_c_distance_softtrim','r12_c_and_validation_distance'), range(1,13)))
R13_MODE_NUMBERS = {'r13_keep_hit_uniform': 1, 'r13_keep_hit_spatial': 2}
R14_REVISION = 'R14-NF-168-v3'
R14_NUMBERING = 'compact-15-v1'
# Public numbering was compacted at the user's request; algorithms/runtime
# names are unchanged. Old public numbers are provenance, never numeric aliases.
R14_MODE_SPECS = {
    'r14_g2_none_equal': (1, 2, 'NONE', 2, None),
    'r14_g4_none_equal': (2, 4, 'NONE', 4, None),
    'r14_g2_none_half': (3, 2, 'NONE', 1, None),
    'r14_g4_none_half': (4, 4, 'NONE', 2, None),
    'r14_g2_none_zero': (5, 2, 'NONE', 0, None),
    'r14_g4_none_zero': (6, 4, 'NONE', 0, None),
    'r14_fixed_near_only': (7, 2, 'fixed', 0, None),
    'r14_fixed_quarter': (8, 4, 'fixed', 1, None),
    'r14_fixed_threequarter': (9, 4, 'fixed', 3, None),
    'r14_g2_pair2_equal': (10, 2, 'PAIR2', 2, 5),
    'r14_g4_pair2_equal': (11, 4, 'PAIR2', 4, 9),
    'r14_g2_pair2_half': (12, 2, 'PAIR2', 1, 2),
    'r14_g4_pair2_half': (13, 4, 'PAIR2', 2, 4),
    'r14_g2_pair2_zero': (14, 2, 'PAIR2', 0, 0),
    'r14_g4_pair2_zero': (15, 4, 'PAIR2', 0, 0),
}
R14_MODE_NUMBERS = {name: spec[0] for name, spec in R14_MODE_SPECS.items()}
R14_LEGACY_PUBLIC_MODES = dict(zip(R14_MODE_SPECS, (1, 4, 7, 10, 13, 16, 19, 20, 21, 22, 23, 24, 25, 26, 27)))
R14_PHASE_A = (7, 1, 10, 8, 9, 2, 11)
R14_PHASE_B = (3, 4, 5, 6, 12, 13, 14, 15)


def r14_protocol(mode: str) -> dict:
    """Frozen algorithm identity, distinct from observed execution/build facts."""
    public, k, update, r0, s0 = R14_MODE_SPECS[mode]
    return {
        'revision': R14_REVISION, 'numbering': R14_NUMBERING,
        'public_mode': public, 'legacy_public_mode': R14_LEGACY_PUBLIC_MODES[mode], 'internal_policy': 99 + public,
        'runtime': mode, 'macro': 'JVET_BJUT_TS_R14_MODE', 'anchor': 'current',
        'mechanism_controls': ['r13_keep_hit_uniform', 'r13_keep_hit_spatial'],
        'K': k, 'grid': [r0] if update == 'fixed' else list(range(k + 1)),
        'update': update, 'r0': r0, 's0': s0,
        'rho': '21/2', 'score_scale': 168,
        'physical_slots': ['L', 'U', 'D', 'LL', 'UU'], 'weights': 'K,K,r,r,r',
        'minimum_nonzero_positions': 3, 'n_includes_zero_weight_positions': True,
        'targetActive': 'TS && !TSRC_disabled && BDPCM==NONE',
        'feedback_cost': 'unscaled syntaxCost(remap(final_abs_q,p))',
        'feedback_tie': ['cost', 'abs(t-r)', '-t'],
        'state_scope': 'TU-local per component/trial; CG all-zero rollback',
        'phase': 'A' if public in R14_PHASE_A else 'B',
    }


R15_REVISION = 'R15-CODEC-v1'
R15_NUMBERING = 'compact-18-v1'
R15_MODE_NUMBERS = dict(zip((
    'r15_identity', 'r15_g_eq_k2', 'r15_g_eq_k3', 'r15_g_eq_k4', 'r15_g_eq_k6',
    'r15_n_eq_k2', 'r15_n_eq_k3', 'r15_n_eq_k4', 'r15_n_eq_k6',
    'r15_p_eq_k2', 'r15_p_eq_k3', 'r15_p_eq_k6', 'r15_d_eq_k2', 'r15_d_eq_k3',
    'r15_x_eq_k2', 'r15_x_eq_k3', 'r15_g_sp_k3', 'r15_n_sp_k3'), range(1, 19)))


def r15_protocol(mode: str) -> dict:
    public = R15_MODE_NUMBERS[mode]
    parts = mode.split('_')
    return {
        'revision': R15_REVISION, 'numbering': R15_NUMBERING,
        'mapping': 'TS-MG-STATIC-FAST-v1', 'public_mode': public,
        'MG': 1 if public == 1 else public + 2, 'internal_policy': 114 + public,
        'runtime': mode, 'macro': 'JVET_BJUT_TS_R15_MODE', 'anchor': 'current',
        'search': 'I' if public == 1 else parts[1].upper(),
        'K': 0 if public == 1 else int(parts[3][1:]),
        'weights': [2, 2, 1, 1, 1] if public >= 17 else [1, 1, 1, 1, 1],
        'physical_slots': ['L', 'U', 'D', 'LL', 'UU'],
        'minimum_nonzero_positions': 0 if public == 1 else 3,
        'engine': 'PREFIX', 'score': 'integer-syntax', 'state': 'none',
        'targetActive': 'TS && !TSRC_disabled && BDPCM==NONE',
        'quant_search': 'map-up-to-1', 'mode_bits': 0,
    }


def directory_name(mode: str) -> str:
    if mode in R15_MODE_NUMBERS:
        return f'r15_{R15_MODE_NUMBERS[mode]}_{mode.removeprefix("r15_")}'
    if mode in R14_MODE_NUMBERS:
        return f'r14_{R14_MODE_NUMBERS[mode]}_{mode.removeprefix("r14_")}'
    if mode in R13_MODE_NUMBERS:
        return f'r13_{R13_MODE_NUMBERS[mode]}_{mode.removeprefix("r13_")}'
    if mode in R12_MODE_NUMBERS:
        return f'r12_{R12_MODE_NUMBERS[mode]}_{mode.removeprefix("r12_")}'
    if mode in R11_MODE_NUMBERS:
        return f'r11_{R11_MODE_NUMBERS[mode]}_{mode.removeprefix("r11_")}'
    if mode in R10_MODE_NUMBERS:
        return f'r10_{R10_MODE_NUMBERS[mode]}_{mode.removeprefix("r10_")}'
    if mode in R9_MODE_NUMBERS:
        return f'r9_{R9_MODE_NUMBERS[mode]}_{mode.removeprefix("r9_")}'
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
