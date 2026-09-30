"""Paired reporting utilities with exact Poisson intervals."""
import math
import re


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


def _pair_key(row):
    common = ("schema_version", "schema_minor", "game_id", "game_tree_spec", "game_sha", "harness_sha", "persona_id",
              "persona_prompt_sha256", "seed", "turn_cap", "turn_policy",
              "narrator_policy", "is_holdout",
              "measurement_policy", "severity_taxonomy_version", "detector_version", "golem_model",
              "golem_effort")
    values = []
    golem = row.get("golem") or {}
    for key in common:
        if key == "schema_minor": value = row.get(key, 0)
        elif key == "game_id": value = row.get(key, "dnd_combat")
        elif key == "game_tree_spec": value = row.get(key, "dnd_combat/*.py")
        else: value = golem.get(key.removeprefix("golem_")) if key.startswith("golem_") else row.get(key)
        if value is None or value == "": return None
        values.append(value)
    if row.get("measurement_policy") == "detector_and_judge" and row.get("judge_status") != "COMPLETE":
        return None
    if row.get("measurement_policy") == "detector_and_judge":
        for key in ("judge_version", "verifier_version", "judge_model", "judge_effort"):
            value = row.get(key)
            if value is None or value == "": return None
            values.append(value)
    holdout_hash = row.get("holdout_prompt_sha256")
    if row.get("is_holdout") is True and not holdout_hash: return None
    if row.get("is_holdout") is False and holdout_hash is not None: return None
    values.append(holdout_hash)
    if row.get("measurement_policy") == "detector_only" and row.get("judge_status") != "NOT_REQUESTED":
        return None
    return tuple(values)


def compare(baseline_entries, candidate_entries, coverage_fraction=1.0):
    """Pair only complete, identity-bound v2 evidence with equal initial catalogs."""
    if coverage_fraction < 0: raise ValueError("coverage_fraction must be nonnegative")
    base, cand = list(baseline_entries), list(candidate_entries)
    pairs, ineligible = [], []
    eligible_left, eligible_right = [], []
    for side, rows, output in (("baseline", base, eligible_left), ("candidate", cand, eligible_right)):
        for row in rows:
            run_id = row.get("run_id")
            if row.get("schema_version") != 2:
                ineligible.append({"run_id": run_id, "reason": "LEGACY_SCHEMA"}); continue
            if row.get("detector_set_status", "IMPLEMENTED") != "IMPLEMENTED":
                ineligible.append({"run_id": run_id, "reason": "DETECTORS_NOT_IMPLEMENTED_FOR_GAME"}); continue
            if not row.get("eligibility", {}).get("comparison_eligible", row.get("run_outcome") == "COMPLETE"):
                ineligible.append({"run_id": run_id, "reason": row.get("eligibility", {}).get("reason_code", "RUN_INELIGIBLE")}); continue
            if row.get("turns", 0) <= 0:
                ineligible.append({"run_id": run_id, "reason": "ZERO_ACTION_TURNS"}); continue
            if row.get("turn_cap") is None:
                ineligible.append({"run_id": run_id, "reason": "TURN_CAP_UNKNOWN"}); continue
            key = _pair_key(row)
            catalog = row.get("content_catalog")
            if key is None:
                ineligible.append({"run_id": run_id, "reason": "PAIR_IDENTITY_MISSING"}); continue
            if not isinstance(catalog, dict) or catalog.get("catalog_version") != 1:
                ineligible.append({"run_id": run_id, "reason": "CONTENT_CATALOG_MISSING"}); continue
            expected = row.get("expected_content_change")
            if isinstance(expected, str) and expected.strip():
                ineligible.append({"run_id": run_id, "reason": "NOT_A_LIKE_FOR_LIKE", "expected_content_change": expected}); continue
            output.append((key, row))
    left_by_key, right_by_key = {}, {}
    for key, row in eligible_left: left_by_key.setdefault(key, []).append(row)
    for key, row in eligible_right: right_by_key.setdefault(key, []).append(row)
    duplicate = set(key for key, rows in left_by_key.items() if len(rows) > 1)
    duplicate.update(key for key, rows in right_by_key.items() if len(rows) > 1)
    used_left, used_right = set(), set()
    for key in duplicate:
        for row in left_by_key.get(key, []) + right_by_key.get(key, []):
            used_left.add(id(row)); used_right.add(id(row))
            ineligible.append({"run_id": row.get("run_id"), "reason": "DUPLICATE_PAIR_KEY", "pair_key": key})
    for key, left_rows in left_by_key.items():
        if key in duplicate: continue
        right_rows = right_by_key.get(key, [])
        if not right_rows: continue
        left, right = left_rows[0], right_rows[0]
        if left.get("expected_content_change") or right.get("expected_content_change"):
            ineligible.append({"baseline_run_id": left.get("run_id"), "candidate_run_id": right.get("run_id"), "reason": "NOT_A_LIKE_FOR_LIKE"}); continue
        bc, cc = left.get("coverage", {}), right.get("coverage", {})
        losses = [field for field in ("rooms_visited", "objects_touched", "encounters_faced")
                  if cc.get(field, 0) < coverage_fraction * bc.get(field, 0)]
        if losses:
            ineligible.append({"baseline_run_id": left.get("run_id"), "candidate_run_id": right.get("run_id"),
                               "reason": "COMPARISON_INELIGIBLE_CONTENT_LOSS", "coverage_fields": losses}); continue
        if left["catalog_sha256"] != right["catalog_sha256"]:
            ineligible.append({"baseline_run_id": left.get("run_id"), "candidate_run_id": right.get("run_id"), "reason": "CONTENT_CATALOG_MISMATCH"}); continue
        pairs.append({"baseline": left, "candidate": right})
        used_left.add(id(left)); used_right.add(id(right))
    for _, row in eligible_left:
        if id(row) not in used_left and not any(item.get("run_id") == row.get("run_id") for item in ineligible):
            ineligible.append({"run_id": row.get("run_id"), "reason": "NO_MATCHING_CANDIDATE"})
    for _, row in eligible_right:
        if id(row) not in used_right and not any(item.get("run_id") == row.get("run_id") for item in ineligible):
            ineligible.append({"run_id": row.get("run_id"), "reason": "UNPAIRED_CANDIDATE"})
    ineligible.sort(key=lambda row: (str(row.get("run_id", row.get("baseline_run_id", ""))), row["reason"]))
    modes = set(); static_modes = set(); inconclusive = {}
    for pair in pairs:
        for side in ("baseline", "candidate"):
            for item in pair[side].get("verified_instances", []):
                label = f"{item['source']}:{item['mode']}"
                (static_modes if item["evidence_kind"] == "static_probe" else modes).add(label)
            for note in pair[side].get("detector_notes", []):
                if note.get("kind") == "INCONCLUSIVE":
                    label = f"detector:{note['mode']}"
                    inconclusive[label] = inconclusive.get(label, 0) + 1
                    modes.add(label)
    mode_rows = {}; overlap = False
    for label in sorted(modes):
        source, mode = label.split(":", 1)
        def count(entry):
            return sum(1 for item in entry.get("verified_instances", [])
                       if item["source"] == source and item["mode"] == mode
                       and item["evidence_kind"] == "transcript")
        bcount = sum(count(p["baseline"]) for p in pairs)
        ccount = sum(count(p["candidate"]) for p in pairs)
        bt = sum(p["baseline"].get("turns", 0) for p in pairs)
        ct = sum(p["candidate"].get("turns", 0) for p in pairs)
        if label in inconclusive:
            mode_rows[label] = {"baseline_count": bcount, "candidate_count": ccount,
                "baseline_rate_per_100": None, "candidate_rate_per_100": None,
                "baseline_ci_per_100": None, "candidate_ci_per_100": None,
                "paired_delta_count": None, "inconclusive_count": inconclusive[label],
                "rate_status": "not established (inconclusive evidence)"}
        else:
            bci, cci = poisson_ci(bcount), poisson_ci(ccount)
            rate_ci_b = tuple(100 * x / bt for x in bci); rate_ci_c = tuple(100 * x / ct for x in cci)
            intersects = max(rate_ci_b[0], rate_ci_c[0]) <= min(rate_ci_b[1], rate_ci_c[1])
            overlap |= intersects
            mode_rows[label] = {"baseline_count": bcount, "candidate_count": ccount,
                "baseline_rate_per_100": rate_per_100(bcount, bt), "candidate_rate_per_100": rate_per_100(ccount, ct),
                "baseline_ci_per_100": rate_ci_b, "candidate_ci_per_100": rate_ci_c,
                "paired_delta_count": ccount-bcount, "inconclusive_count": 0, "rate_status": None}
    static_rows = {}
    for label in sorted(static_modes):
        source, mode = label.split(":", 1)
        static_rows[label] = {"baseline_count": sum(1 for pair in pairs for item in pair["baseline"].get("verified_instances", [])
                                   if item["source"] == source and item["mode"] == mode and item["evidence_kind"] == "static_probe"),
                              "candidate_count": sum(1 for pair in pairs for item in pair["candidate"].get("verified_instances", [])
                                   if item["source"] == source and item["mode"] == mode and item["evidence_kind"] == "static_probe")}
    curiosity = [{"baseline": pair["baseline"].get("curiosity", {}), "candidate": pair["candidate"].get("curiosity", {})} for pair in pairs]
    zeros = [mode for mode, row in mode_rows.items() if row["baseline_count"] == row["candidate_count"] == 0 and mode not in inconclusive]
    return {"paired_count": len(pairs), "pairs": pairs, "ineligible": ineligible, "per_mode": mode_rows,
            "static_probe_counts": static_rows, "curiosity_separate": curiosity,
            "evidence_statement": "not enough evidence to claim improvement" if overlap or not pairs else "paired intervals do not overlap; interpret cautiously",
            "zero_statement": "zero verified instances" if zeros and not inconclusive else None, "zero_modes": zeros,
            "inconclusive_modes": inconclusive,
            "sample_size_note": "Single-cycle model-player rates are problem discovery, not measurement; trend claims need repeated paired seeds."}


CROSS_GAME_MODE_MAP = {
    "UNRECOGNIZED_COMMAND": "UNRECOGNIZED_COMMAND",
    "UNSUPPORTED_INTENT": "UNSUPPORTED_INTENT",
    "REPEATED_RESPONSE": "REPEATED_RESPONSE",
    "NO_CONSEQUENCE_STALL": "NO_CONSEQUENCE_STALL",
    "DOMINANT_ACTION": "DOMINANT_ACTION",
    "DOMINANT_ACTION_SOFT": "DOMINANT_ACTION_SOFT",
    "FAIL_WITH_NOTHING": "FAIL_WITH_NOTHING",
}


def compare_cross_game(baseline_entries, candidate_entries, spec):
    """Descriptive cross-game pairing under an explicit, audited change declaration."""
    required = {"baseline_game_sha", "candidate_game_sha", "baseline_game_id",
                "candidate_game_id", "permitted_changes"}
    if not isinstance(spec, dict) or set(spec) != required:
        raise ValueError("cross-game spec must declare both game identities and permitted_changes")
    if spec["baseline_game_id"] == spec["candidate_game_id"]:
        raise ValueError("cross-game comparison requires distinct game ids")
    if any(value not in {"dnd_combat", "delve"} for value in
           (spec["baseline_game_id"], spec["candidate_game_id"])):
        raise ValueError("unsupported cross-game game id")
    for field in ("baseline_game_sha", "candidate_game_sha"):
        if not isinstance(spec[field], str) or not re.fullmatch(r"[0-9a-f]{64}", spec[field]):
            raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    if not isinstance(spec["permitted_changes"], list) or any(not isinstance(x, str) or not x.strip() for x in spec["permitted_changes"]):
        raise ValueError("permitted_changes must be a list of nonempty strings")
    for side, rows, game_id, game_sha in (
            ("baseline", baseline_entries, spec["baseline_game_id"], spec["baseline_game_sha"]),
            ("candidate", candidate_entries, spec["candidate_game_id"], spec["candidate_game_sha"])):
        for row in rows:
            if row.get("game_id", "dnd_combat") != game_id or row.get("game_sha") != game_sha:
                raise ValueError(f"{side} entries do not match declared game identity")
    dimensions = ("persona_id", "seed", "turn_cap", "turn_policy", "narrator_policy",
                  "is_holdout", "measurement_policy")
    key = lambda row: tuple(row.get(field) for field in dimensions)
    def keyed(rows, label):
        result = {}
        for row in rows:
            pairing = key(row)
            if any(value is None for value in pairing): raise ValueError(f"{label} entry lacks cross-game pairing identity")
            if pairing in result: raise ValueError(f"duplicate {label} cross-game pairing identity")
            result[pairing] = row
        return result
    left = keyed(baseline_entries, "baseline")
    right = keyed(candidate_entries, "candidate")
    pairs = [{"baseline": left[k], "candidate": right[k]} for k in sorted(left.keys() & right.keys(), key=repr)]
    rates_implemented = all(
        pair[side].get("detector_set_status", "IMPLEMENTED") == "IMPLEMENTED"
        for pair in pairs for side in ("baseline", "candidate"))
    mode_deltas = None
    if rates_implemented and pairs:
        shared = set(CROSS_GAME_MODE_MAP)
        for side in ("baseline", "candidate"):
            expected = "1" if spec[side + "_game_id"] == "dnd_combat" else "delve-1"
            if any(pair[side].get("detector_version") != expected for pair in pairs):
                shared.clear()
        labels = [("detector", mode) for mode in sorted(shared)]
        mode_deltas = {}
        for source, mode in labels:
            unresolved = sum(1 for pair in pairs for side in ("baseline", "candidate")
                             for note in pair[side].get("detector_notes", [])
                             if source == "detector" and note.get("kind") == "INCONCLUSIVE" and note.get("mode") == mode)
            if unresolved:
                mode_deltas[f"{source}:{mode}"] = {"baseline_rate_per_100": None,
                    "candidate_rate_per_100": None, "descriptive_delta_per_100": None,
                    "inconclusive_count": unresolved,
                    "rate_status": "not established (inconclusive evidence)"}
                continue
            counts, turns = [], []
            for side in ("baseline", "candidate"):
                count = sum(1 for pair in pairs for item in pair[side].get("verified_instances", [])
                            if item.get("source") == source and item.get("mode") == mode and item.get("evidence_kind") == "transcript")
                denominator = sum(pair[side].get("turns", 0) for pair in pairs)
                counts.append(count); turns.append(denominator)
            mode_deltas[f"{source}:{mode}"] = {"baseline_rate_per_100": rate_per_100(counts[0], turns[0]),
                "candidate_rate_per_100": rate_per_100(counts[1], turns[1]),
                "descriptive_delta_per_100": rate_per_100(counts[1], turns[1]) - rate_per_100(counts[0], turns[0]),
                "rate_status": "descriptive only"}
    return {"comparison_type": "CROSS_GAME", "paired_count": len(pairs), "pairs": pairs,
            "unpaired_baseline": len(left.keys() - right.keys()), "unpaired_candidate": len(right.keys() - left.keys()),
            "mode_rate_deltas": mode_deltas,
            "label": "CROSS_GAME: not like-for-like; descriptive only; no improvement claim",
            "baseline_game_id": spec["baseline_game_id"], "candidate_game_id": spec["candidate_game_id"],
            "baseline_game_sha": spec["baseline_game_sha"], "candidate_game_sha": spec["candidate_game_sha"],
            "permitted_changes": list(spec["permitted_changes"])}

def render_markdown(report):
    lines = ["# Paired playtest comparison", "", f"Paired runs: {report['paired_count']}", "",
             "| Source:mode | Baseline raw | Candidate raw | Baseline /100 (95% CI) | Candidate /100 (95% CI) | Paired delta |",
             "|---|---:|---:|---:|---:|---:|"]
    for mode, row in sorted(report["per_mode"].items()):
        label = f"{mode} INCONCLUSIVE({row['inconclusive_count']})" if row.get("inconclusive_count") else mode
        if row.get("rate_status"):
            baseline_rate = candidate_rate = row["rate_status"]
            delta = "withheld"
        else:
            bci, cci = row["baseline_ci_per_100"], row["candidate_ci_per_100"]
            baseline_rate = f"{row['baseline_rate_per_100']:.2f} ({bci[0]:.2f}–{bci[1]:.2f})"
            candidate_rate = f"{row['candidate_rate_per_100']:.2f} ({cci[0]:.2f}–{cci[1]:.2f})"
            delta = f"{row['paired_delta_count']:+d}"
        lines.append(f"| {label} | {row['baseline_count']} | {row['candidate_count']} | {baseline_rate} | {candidate_rate} | {delta} |")
    if report.get("static_probe_counts"):
        lines += ["", "Static probe instances (not action-turn rates)", ""]
        for mode, row in sorted(report["static_probe_counts"].items()):
            lines.append(f"- {mode}: baseline {row['baseline_count']}, candidate {row['candidate_count']}")
    lines += ["", f"Evidence: {report['evidence_statement']}.", report["sample_size_note"], "",
              "Curiosity counters (DISCOVERY, EARNED_CONSEQUENCE, CALLBACK) are reported separately and are not combined with detector counts."]
    if report.get("zero_statement"): lines.append(report["zero_statement"])
    if report["ineligible"]:
        lines += ["", "## Ineligible runs"]
        lines.extend(f"- {row.get('run_id', row.get('candidate_run_id', 'unknown'))}: {row['reason']}" for row in report["ineligible"])
    return "\n".join(lines) + "\n"
