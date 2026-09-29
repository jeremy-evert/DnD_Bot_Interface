"""Paired reporting utilities with exact Poisson intervals."""
import math


def rate_per_100(count, turns):
    return 100.0 * count / turns if turns else 0.0


def _regularized_gamma_p(a, x):
    if x <= 0:
        return 0.0
    gln = math.lgamma(a)
    if x < a + 1:
        ap, term, total = a, 1.0 / a, 1.0 / a
        for _ in range(10000):
            ap += 1
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return total * math.exp(-x + a * math.log(x) - gln)
    b = x + 1 - a
    c, d, h = 1e300, 1 / b, 1 / b
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < 1e-300: d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300: c = 1e-300
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15: break
    q = math.exp(-x + a * math.log(x) - gln) * h
    return 1 - q


def poisson_ci(count, confidence=0.95):
    """Garwood exact interval for a Poisson count (count, not a rate)."""
    if type(count) is not int or count < 0 or not 0 < confidence < 1:
        raise ValueError("count must be nonnegative int and confidence between zero and one")
    alpha = 1 - confidence
    def gamma_quantile(shape, probability):
        lo, hi = 0.0, max(1.0, shape * 2 + 10)
        while _regularized_gamma_p(shape, hi) < probability:
            hi *= 2
        for _ in range(100):
            mid = (lo + hi) / 2
            if _regularized_gamma_p(shape, mid) < probability: lo = mid
            else: hi = mid
        return (lo + hi) / 2
    lower = 0.0 if count == 0 else gamma_quantile(count, alpha / 2)
    upper = gamma_quantile(count + 1, 1 - alpha / 2)
    return lower, upper


def _key(row):
    return tuple(row.get(k) for k in ("persona_id", "seed", "turn_cap", "narrator_policy", "is_holdout", "detector_version"))


def compare(baseline_entries, candidate_entries, coverage_fraction=1.0):
    """Pair exact matched runs; retain every unmatched or unusable row as ineligible."""
    if coverage_fraction < 0:
        raise ValueError("coverage_fraction must be nonnegative")
    base, cand = list(baseline_entries), list(candidate_entries)
    left_by_key, right = {}, {}
    for row in base: left_by_key.setdefault(_key(row), []).append(row)
    for row in cand: right.setdefault(_key(row), []).append(row)
    pairs, ineligible = [], []
    duplicate_keys = {key for key, rows in left_by_key.items() if len(rows) > 1}
    duplicate_keys.update(key for key, rows in right.items() if len(rows) > 1)
    duplicate_ids = set()
    for key in duplicate_keys:
        for row in left_by_key.get(key, []) + right.get(key, []):
            duplicate_ids.add(id(row))
            ineligible.append({"run_id": row.get("run_id"), "reason": "DUPLICATE_PAIR_KEY", "pair_key": key})
    used = set(duplicate_ids)
    for left in base:
        if id(left) in duplicate_ids: continue
        if not left.get("eligibility", {}).get("comparison_eligible", left.get("run_outcome") == "COMPLETE"):
            ineligible.append({"run_id": left.get("run_id"), "reason": left.get("eligibility", {}).get("reason_code", "BASELINE_INELIGIBLE")}); continue
        if left.get("turn_cap") is None:
            ineligible.append({"run_id": left.get("run_id"), "reason": "TURN_CAP_UNKNOWN"}); continue
        key = _key(left)
        matches = right.get(key, [])
        match = next((x for x in matches if id(x) not in used), None)
        if match is None:
            ineligible.append({"run_id": left.get("run_id"), "reason": "NO_MATCHING_CANDIDATE", "pair_key": key}); continue
        used.add(id(match))
        if not match.get("eligibility", {}).get("comparison_eligible", match.get("run_outcome") == "COMPLETE"):
            ineligible.append({"run_id": match.get("run_id"), "reason": match.get("eligibility", {}).get("reason_code", "CANDIDATE_INELIGIBLE")}); continue
        if match.get("turn_cap") is None:
            ineligible.append({"run_id": match.get("run_id"), "reason": "TURN_CAP_UNKNOWN"}); continue
        expected_change = left.get("expected_content_change") or match.get("expected_content_change")
        if not isinstance(expected_change, str) or not expected_change.strip(): expected_change = None
        if expected_change:
            ineligible.append({"baseline_run_id": left.get("run_id"), "candidate_run_id": match.get("run_id"),
                               "reason": "NOT_A_LIKE_FOR_LIKE", "expected_content_change": expected_change})
            continue
        bc, cc = left.get("coverage", {}), match.get("coverage", {})
        losses = [field for field in ("rooms_visited", "objects_touched", "encounters_faced")
                  if cc.get(field, 0) < coverage_fraction * bc.get(field, 0)]
        if losses:
            ineligible.append({"baseline_run_id": left.get("run_id"), "candidate_run_id": match.get("run_id"),
                               "reason": "COMPARISON_INELIGIBLE_CONTENT_LOSS", "coverage_fields": losses})
            continue
        inventory_b, inventory_c = left.get("content_inventory"), match.get("content_inventory")
        if inventory_b is not None and inventory_c is not None:
            inventory_losses = [field for field in ("total_rooms", "total_objects", "total_takeables", "total_enemies", "total_exits")
                                if inventory_c.get(field, 0) < inventory_b.get(field, 0)]
            if inventory_losses:
                ineligible.append({"baseline_run_id": left.get("run_id"), "candidate_run_id": match.get("run_id"),
                                   "reason": "COMPARISON_INELIGIBLE_CONTENT_LOSS", "inventory_fields": inventory_losses})
                continue
        pairs.append({"baseline": left, "candidate": match})
    for row in cand:
        if id(row) not in used and not any(x.get("run_id") == row.get("run_id") for x in ineligible):
            ineligible.append({"run_id": row.get("run_id"), "reason": "UNPAIRED_CANDIDATE"})
    ineligible.sort(key=lambda row: (str(row.get("run_id", row.get("baseline_run_id", ""))), row["reason"]))
    modes = set()
    for pair in pairs:
        for side in ("baseline", "candidate"):
            for source, values in pair[side].get("per_mode_verified_instances", {}).items():
                modes.update(f"{source}:{mode}" for mode in values)
    mode_rows = {}
    overlap = False
    for label in sorted(modes):
        source, mode = label.split(":", 1)
        bcount = sum(p["baseline"].get("per_mode_verified_instances", {}).get(source, {}).get(mode, 0) for p in pairs)
        ccount = sum(p["candidate"].get("per_mode_verified_instances", {}).get(source, {}).get(mode, 0) for p in pairs)
        bt = sum(p["baseline"].get("turns", 0) for p in pairs); ct = sum(p["candidate"].get("turns", 0) for p in pairs)
        bci, cci = poisson_ci(bcount), poisson_ci(ccount)
        rate_ci_b = tuple(100 * x / bt for x in bci) if bt else (0, 0)
        rate_ci_c = tuple(100 * x / ct for x in cci) if ct else (0, 0)
        intersects = max(rate_ci_b[0], rate_ci_c[0]) <= min(rate_ci_b[1], rate_ci_c[1])
        overlap |= intersects
        mode_rows[label] = {"baseline_count": bcount, "candidate_count": ccount,
                            "baseline_rate_per_100": rate_per_100(bcount, bt), "candidate_rate_per_100": rate_per_100(ccount, ct),
                            "baseline_ci_per_100": rate_ci_b, "candidate_ci_per_100": rate_ci_c,
                            "paired_delta_count": ccount - bcount}
    curiosity = [{"baseline": p["baseline"].get("curiosity", {}), "candidate": p["candidate"].get("curiosity", {})} for p in pairs]
    zero_modes = [mode for mode, row in mode_rows.items() if row["baseline_count"] == row["candidate_count"] == 0]
    return {"paired_count": len(pairs), "pairs": pairs, "ineligible": ineligible, "per_mode": mode_rows,
            "curiosity_separate": curiosity,
            "evidence_statement": "not enough evidence to claim improvement" if overlap or not pairs else "paired intervals do not overlap; interpret cautiously",
            "zero_statement": "zero verified instances" if zero_modes else None, "zero_modes": zero_modes,
            "sample_size_note": "Single-cycle model-player rates are problem discovery, not measurement; trend claims need repeated paired seeds."}


def render_markdown(report):
    lines = ["# Paired playtest comparison", "", f"Paired runs: {report['paired_count']}", "",
             "| Source:mode | Baseline raw | Candidate raw | Baseline /100 (95% CI) | Candidate /100 (95% CI) | Paired delta |",
             "|---|---:|---:|---:|---:|---:|"]
    for mode, row in sorted(report["per_mode"].items()):
        bci, cci = row["baseline_ci_per_100"], row["candidate_ci_per_100"]
        lines.append(f"| {mode} | {row['baseline_count']} | {row['candidate_count']} | {row['baseline_rate_per_100']:.2f} ({bci[0]:.2f}–{bci[1]:.2f}) | {row['candidate_rate_per_100']:.2f} ({cci[0]:.2f}–{cci[1]:.2f}) | {row['paired_delta_count']:+d} |")
    lines += ["", f"Evidence: {report['evidence_statement']}.", report["sample_size_note"], "",
              "Curiosity counters (DISCOVERY, EARNED_CONSEQUENCE, CALLBACK) are reported separately and are not combined with detector counts."]
    if report.get("zero_statement"): lines.append(report["zero_statement"])
    if report["ineligible"]:
        lines += ["", "## Ineligible runs"]
        lines.extend(f"- {row.get('run_id', row.get('candidate_run_id', 'unknown'))}: {row['reason']}" for row in report["ineligible"])
    return "\n".join(lines) + "\n"
