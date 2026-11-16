from __future__ import annotations

import re
from functools import lru_cache
from statistics import median
from collections import defaultdict
from typing import Any, Iterable

from app.services.hardware_matching import model_key

# Exact model tokens only. Family names and generic GHz/core-count statements
# are intentionally handled separately and never promoted to a random SKU.
_MODEL_TOKEN = re.compile(
    r"(?i)"
    r"(?<![a-z0-9])(?:intel\s+)?(?:core\s*)?i[3579]\s*[- ]?\s*\d{3,5}[a-z0-9]{0,5}(?![a-z0-9])"
    r"|(?<![a-z0-9])(?:amd\s+)?ryzen\s*[3579]\s*[- ]?\s*\d{4,5}[a-z0-9]{0,5}(?![a-z0-9])"
    r"|(?<![a-z0-9])r[3579]\s*[- ]?\s*\d{4,5}[a-z0-9]{0,5}(?![a-z0-9])"
    r"|(?<![a-z0-9])(?:amd\s+)?fx\s*[- ]?\s*\d{3,4}[a-z]{0,2}(?![a-z0-9])"
    r"|(?<![a-z0-9])(?:amd\s+)?phenom(?:\s+ii)?\s+x?[234]\s*[- ]?\s*\d{3,4}[a-z]{0,2}(?![a-z0-9])"
    r"|(?<![a-z0-9])(?:intel\s+)?core\s*2\s+(?:duo|quad)\s+[eq]\s*\d{3,4}(?![a-z0-9])"
)
_INTEL_FAMILY = re.compile(r"(?i)\b(?:intel\s+)?(?:core\s*)?i([3579])\b")
_RYZEN_FAMILY = re.compile(r"(?i)\b(?:amd\s+)?ryzen\s*([3579])\b|\br([3579])\s*\d{4,5}")
_GEN = re.compile(r"(?i)\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:gen(?:eration)?|generation)\b|\b(\d{1,2})\s*[- ]?gen\b")
_SERIES = re.compile(r"(?i)\b(\d{4})\s*(?:series|series processors)\b")


def _clean(text: str | None) -> str:
    value = str(text or "").replace("\ufffd", " ").replace("\u00a0", " ")
    value = re.sub(r"[®™]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _signature(text: str) -> str:
    key = model_key(_clean(text))
    key = re.sub(r"^(?:intel|amd)", "", key)
    key = re.sub(r"^core(?=i[3579])", "", key)
    key = re.sub(r"^r(?=[3579]\d{4,5})", "ryzen", key)
    return key


def _models(text: str) -> list[dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    cleaned = _clean(text)
    for match in _MODEL_TOKEN.finditer(cleaned):
        tail = cleaned[match.end():]
        # "i5 4000 series" and "Ryzen 5 2000 series" name a generation,
        # not an exact CPU SKU.
        if re.match(r"\s*series\b", tail, re.I):
            continue
        token = _clean(match.group(0))
        suffix = re.match(r"\s*(x3d|x|xt|ge|gt|g|hs|hx|h|u|kf|ks|k|f|t|s|e|c)\b", tail, re.I)
        if suffix:
            token = f"{token}{suffix.group(1)}"
        signature = _signature(token)
        if signature:
            found.setdefault(signature, {"token": token, "signature": signature})
    return list(found.values())


def _family_requirements(text: str) -> list[dict[str, Any]]:
    value = _clean(text)
    families: list[dict[str, Any]] = []
    generations = [int(a or b) for a, b in _GEN.findall(value)]
    series = [int(item) for item in _SERIES.findall(value)]
    for match in _INTEL_FAMILY.finditer(value):
        number = int(match.group(1))
        context = value[max(0, match.start() - 28):match.end() + 36]
        explicit_gen = _GEN.search(context)
        generation = int(next(group for group in explicit_gen.groups() if group)) if explicit_gen else None
        if generation is None and generations and re.search(r"(?i)\b(?:intel|core|i[3579])\b", context):
            generation = generations[0]
        if generation is None and series and re.search(r"(?i)\b(?:intel|core|i[3579])\b", context):
            generation = series[0] // 1000 if series[0] >= 1000 else series[0]
        item = {"vendor": "intel", "family": f"i{number}", "generation": generation}
        if item not in families:
            families.append(item)
    for match in _RYZEN_FAMILY.finditer(value):
        number = int(match.group(1) or match.group(2))
        context = value[max(0, match.start() - 28):match.end() + 36]
        explicit_gen = _GEN.search(context)
        generation = int(next(group for group in explicit_gen.groups() if group)) if explicit_gen else None
        if generation is None and series and re.search(r"(?i)\b(?:amd|ryzen|series)\b", context):
            generation = series[0] // 1000
        item = {"vendor": "amd", "family": f"ryzen{number}", "generation": generation}
        if item not in families:
            families.append(item)
    return families


@lru_cache(maxsize=20000)
def parse_cpu_requirement(text: str | None) -> dict[str, Any]:
    """Parse explicit CPU SKU references without guessing from abstract text."""
    raw = _clean(text)
    models = _models(raw)
    families = _family_requirements(raw)
    if models:
        kind = "exact_model_references"
    elif any(family.get("generation") for family in families):
        kind = "family_with_generation"
    elif families:
        kind = "family_without_generation"
    elif re.search(r"(?i)\b(?:cpu|processor|processor or|dual|quad|core|ghz|mhz)\b", raw):
        kind = "abstract_requirement"
    else:
        kind = "unrecognized_requirement"
    return {"raw_text": raw or None, "parse_type": kind, "models": models, "families": families,
            "parser": "pcgb_cpu_requirement_rules_v1"}


def _cpu_rows(cpu_catalog: Iterable[Any]) -> list[dict[str, Any]]:
    rows = []
    for item in cpu_catalog or ():
        if isinstance(item, dict):
            row = {"id": item.get("id"), "name": str(item.get("name") or ""),
                   "raw_score": item.get("raw_score")}
        else:
            row = {"id": getattr(item, "id", None), "name": str(getattr(item, "name", "") or ""),
                   "raw_score": getattr(item, "raw_score", None)}
        if row["name"] and isinstance(row["raw_score"], (int, float)) and row["raw_score"] > 0:
            explicit_models = _models(row["name"])
            row["signature"] = ((item.get("signature") if isinstance(item, dict) else None)
                                or (explicit_models[0]["signature"] if len(explicit_models) == 1
                                    else _signature(row["name"])))
            rows.append(row)
    return rows


def _family_of_name(name: str) -> tuple[str, int | None] | None:
    value = _clean(name)
    intel = re.search(r"(?i)\b(?:intel\s+)?(?:core\s*)?i([3579])\s*[- ]?\s*(\d{3,5})", value)
    if intel:
        digits = intel.group(2)
        generation = int(digits[:2]) if len(digits) >= 5 and digits[:2] in {"10", "11", "12", "13", "14", "15"} else int(digits[0])
        return f"i{intel.group(1)}", generation
    ryzen = re.search(r"(?i)\b(?:amd\s+)?ryzen\s*([3579])\s*[- ]?\s*(\d{4,5})", value)
    if ryzen:
        return f"ryzen{ryzen.group(1)}", int(ryzen.group(2)[0])
    return None


class CpuRequirementResolver:
    """One request-scoped exact index over available CPU catalog rows."""

    def __init__(self, cpu_catalog: Iterable[Any]):
        self.rows = _cpu_rows(cpu_catalog)
        self.by_signature: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_family: dict[tuple[str, int | None], list[dict[str, Any]]] = defaultdict(list)
        for row in self.rows:
            if row["signature"]:
                self.by_signature[row["signature"]].append(row)
            family = _family_of_name(row["name"])
            if family:
                self.by_family[family].append(row)

    def resolve(self, text: str | None) -> dict[str, Any]:
        parsed = parse_cpu_requirement(text)
        if parsed["models"]:
            resolved = []
            unresolved = []
            for candidate in parsed["models"]:
                matches = self.by_signature.get(candidate["signature"], [])
                if matches:
                    scores = [float(row["raw_score"]) for row in matches]
                    # These rows have the same exact parsed SKU signature. Keep
                    # PassMark variation as a range instead of calling the SKU
                    # ambiguous or choosing an arbitrary duplicate catalog row.
                    row = min(matches, key=lambda item: (len(item["name"]), item["name"].casefold(), item["id"] or 0))
                    resolved.append({"id": row["id"], "name": row["name"], "cpu_mark": median(scores),
                                     "cpu_mark_range": [min(scores), max(scores)],
                                     "catalog_entry_count": len(matches),
                                     "matched_token": candidate["token"], "match_type": "exact_catalog_model"})
                else:
                    unresolved.append({"token": candidate["token"],
                                       "reason": "model_not_in_catalog",
                                       "candidate_count": len(matches)})
            if resolved and unresolved:
                status = "partially_resolved"
            elif resolved:
                status = "resolved_exact_models"
            else:
                status = "unmatched"
            scores = [float(item["cpu_mark"]) for item in resolved]
            all_scores = [score for item in resolved
                          for score in (item.get("cpu_mark_range") or [item["cpu_mark"]])]
            return {**parsed, "status": status, "resolved_models": resolved, "unresolved_models": unresolved,
                    "reference_cpu_mark": round(median(scores), 1) if scores else None,
                    "reference_cpu_mark_range": [min(all_scores), max(all_scores)] if all_scores else None,
                    "match_confidence": ("high" if status == "resolved_exact_models" and all(
                                            item["cpu_mark_range"][0] == item["cpu_mark_range"][1]
                                            for item in resolved)
                                         else "medium" if status == "resolved_exact_models" else "low" if resolved else "none"),
                    "match_provenance": "Exact normalized CPU SKU token to local Hardware catalog; duplicate catalog entries are represented as a PassMark score range. CPU Mark is a total CPU score, not Single Thread."}

        family_refs = []
        if parsed["parse_type"] == "family_with_generation":
            for family in parsed["families"]:
                candidates = self.by_family.get((family["family"], family["generation"]), [])
                family_refs.extend({"id": row["id"], "name": row["name"], "cpu_mark": row["raw_score"],
                                    "matched_family": family, "match_type": "family_range_member"}
                                   for row in candidates)
        if family_refs:
            scores = [float(item["cpu_mark"]) for item in family_refs]
            return {**parsed, "status": "resolved_family_range", "resolved_models": family_refs,
                    "unresolved_models": [], "reference_cpu_mark": round(median(scores), 1),
                    "reference_cpu_mark_range": [min(scores), max(scores)],
                    "match_confidence": "low",
                    "match_provenance": "Generation/family match only; this is a broad catalog score range, not one substituted processor."}
        status = "unresolved_family" if parsed["families"] else parsed["parse_type"]
        return {**parsed, "status": status, "resolved_models": [], "unresolved_models": [],
                "reference_cpu_mark": None, "reference_cpu_mark_range": None,
                "match_confidence": "none",
                "match_provenance": "No exact CPU model was identified in the catalog; abstract requirements are not mapped to a substitute."}


@lru_cache(maxsize=8)
def _cached_resolver(fingerprint: tuple[tuple[int | None, str, float], ...]) -> CpuRequirementResolver:
    # Cache only normalized scalar values, never SQLAlchemy objects/sessions.
    return CpuRequirementResolver([
        {"id": row_id, "name": name, "raw_score": score}
        for row_id, name, score in fingerprint
    ])


def resolver_for_catalog(cpu_catalog: Iterable[Any]) -> CpuRequirementResolver:
    rows = _cpu_rows(cpu_catalog)
    fingerprint = tuple(sorted(
        ((int(row["id"]) if row.get("id") is not None else None,
          row["name"], float(row["raw_score"])) for row in rows),
        key=lambda item: (item[0] is None, item[0] or 0, item[1], item[2]),
    ))
    return _cached_resolver(fingerprint)


def resolve_cpu_requirement(text: str | None, cpu_catalog: Iterable[Any]) -> dict[str, Any]:
    return resolver_for_catalog(cpu_catalog).resolve(text)

def _comparison(score: float, reference: dict[str, Any] | None) -> dict[str, Any] | None:
    if not reference or not reference.get("resolved_models"):
        return None
    scores = [float(value) for item in reference["resolved_models"]
              for value in (item.get("cpu_mark_range") or [item["cpu_mark"]])]
    low, high, center = min(scores), max(scores), median(scores)
    return {"index_vs_reference_percent": round(score / center * 100, 1),
            "range_vs_reference_percent": [round(score / high * 100, 1), round(score / low * 100, 1)],
            "reference_cpu_mark": round(center, 1), "reference_cpu_mark_range": [low, high],
            "reference_models": reference["resolved_models"][:8],
            "reference_model_count": len(reference["resolved_models"]),
            "reference_models_truncated": len(reference["resolved_models"]) > 8,
            "reference_status": reference["status"], "reference_confidence": reference["match_confidence"]}


def assess_cpu_adequacy(game_profile: dict[str, Any] | None, cpu: Any,
                        cpu_catalog: Iterable[Any] = ()) -> dict[str, Any]:
    """Compare total PassMark CPU Mark to listed requirement CPU models.

    This is a requirements-relative hardware proxy; it is not an FPS, game CPU
    benchmark, or single-thread score.
    """
    cpu_name = str(getattr(cpu, "name", "") or "")
    score = getattr(cpu, "raw_score", None)
    if not game_profile:
        return {"available": False, "status": "no_game_requirement_data", "cpu_name": cpu_name or None,
                "current_cpu_mark": score, "note": "Для игры нет сохранённых требований CPU."}
    minimum = (game_profile.get("minimum_requirements") or {}).get("cpu")
    recommended = (game_profile.get("recommended_requirements") or {}).get("cpu")
    if not minimum and not recommended:
        return {"available": False, "status": "no_cpu_requirement_data", "cpu_name": cpu_name or None,
                "current_cpu_mark": score, "note": "Источник не опубликовал требования CPU для этой игры."}
    resolver = resolver_for_catalog(cpu_catalog)
    minimum_ref = resolver.resolve(minimum) if minimum else None
    recommended_ref = resolver.resolve(recommended) if recommended else None
    valid_score = isinstance(score, (int, float)) and score > 0
    min_compare = _comparison(float(score), minimum_ref) if valid_score else None
    rec_compare = _comparison(float(score), recommended_ref) if valid_score else None
    status = "unresolved_requirements"
    if valid_score and (min_compare or rec_compare):
        if min_compare:
            min_bounds = min_compare["reference_cpu_mark_range"]
            if float(score) < min_bounds[0]:
                status = "below_minimum_reference_range"
            elif float(score) < min_bounds[1]:
                status = "within_minimum_reference_spread"
            elif rec_compare:
                rec_bounds = rec_compare["reference_cpu_mark_range"]
                status = "between_minimum_and_recommended_ranges" if float(score) < rec_bounds[0] else (
                    "within_recommended_reference_spread" if float(score) < rec_bounds[1] else "at_or_above_recommended_reference_range")
            else:
                status = "at_or_above_minimum_reference_range"
        elif rec_compare:
            bounds = rec_compare["reference_cpu_mark_range"]
            status = "below_recommended_reference_range" if float(score) < bounds[0] else (
                "within_recommended_reference_spread" if float(score) < bounds[1] else "at_or_above_recommended_reference_range")
    unresolved = [entry for reference in (minimum_ref, recommended_ref) if reference
                  for entry in reference.get("unresolved_models", [])]
    return {"available": bool(min_compare or rec_compare), "status": status,
            "cpu_name": cpu_name or None, "current_cpu_mark": score,
            "minimum": min_compare, "recommended": rec_compare,
            "minimum_requirement": minimum, "recommended_requirement": recommended,
            "requirement_source": {"name": "PCGameBenchmarks system requirements",
                                   "url": game_profile.get("source_url"),
                                   "dataset_url": "https://github.com/emilioagustin83/pc-game-fps-dataset",
                                   "snapshot_date": "2026-11-01", "license": "CC BY 4.0"},
            "comparison_scale": "PassMark CPU Mark total score, relative to exact/family CPU requirement references",
            "confidence": "low" if min_compare or rec_compare else "insufficient",
            "unresolved_reference_models": unresolved,
            "note": "Ориентир по системным требованиям. CPU Mark — суммарный балл процессора, не Single Thread и не игровой FPS; он не используется для расчёта FPS или CPU bottleneck."}


def requirement_coverage_summary(profiles: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"games": 0, "minimum_cpu_requirements": 0, "recommended_cpu_requirements": 0,
              "explicit_model_requirement_fields": 0, "family_requirement_fields": 0,
              "abstract_or_unparsed_requirement_fields": 0}
    for profile in profiles:
        counts["games"] += 1
        for field in ("minimum_requirements", "recommended_requirements"):
            text = ((profile.get(field) or {}).get("cpu"))
            if not text:
                continue
            key = "minimum_cpu_requirements" if field.startswith("minimum") else "recommended_cpu_requirements"
            counts[key] += 1
            parsed = parse_cpu_requirement(text)
            if parsed["models"]:
                counts["explicit_model_requirement_fields"] += 1
            elif parsed["families"]:
                counts["family_requirement_fields"] += 1
            else:
                counts["abstract_or_unparsed_requirement_fields"] += 1
    return counts


def requirement_resolution_summary(profiles: Iterable[dict[str, Any]],
                                   cpu_catalog: Iterable[Any]) -> dict[str, int]:
    """Count requirements resolvable against this Hardware catalog.

    Exact, partial and generation-range matches remain separate. Abstract
    descriptions are never mapped to guessed processors.
    """
    resolver = resolver_for_catalog(cpu_catalog)
    counts = {
        "games_with_cpu_requirements": 0,
        "games_with_minimum_requirement_reference": 0,
        "games_with_recommended_requirement_reference": 0,
        "games_with_any_requirement_reference": 0,
        "games_with_both_requirement_references": 0,
        "minimum_fields_resolved_exact_or_partial": 0,
        "recommended_fields_resolved_exact_or_partial": 0,
        "minimum_fields_resolved_by_generation_range": 0,
        "recommended_fields_resolved_by_generation_range": 0,
        "minimum_fields_unresolved": 0,
        "recommended_fields_unresolved": 0,
    }
    for profile in profiles:
        resolved = {}
        has_requirement = False
        for kind, field in (("minimum", "minimum_requirements"),
                            ("recommended", "recommended_requirements")):
            raw = (profile.get(field) or {}).get("cpu")
            if not raw:
                continue
            has_requirement = True
            result = resolver.resolve(raw)
            if result.get("status") in {"resolved_exact_models", "partially_resolved"}:
                counts[f"{kind}_fields_resolved_exact_or_partial"] += 1
                resolved[kind] = True
            elif result.get("status") == "resolved_family_range":
                counts[f"{kind}_fields_resolved_by_generation_range"] += 1
                resolved[kind] = True
            else:
                counts[f"{kind}_fields_unresolved"] += 1
                resolved[kind] = False
        counts["games_with_cpu_requirements"] += int(has_requirement)
        minimum = resolved.get("minimum", False)
        recommended = resolved.get("recommended", False)
        counts["games_with_minimum_requirement_reference"] += int(minimum)
        counts["games_with_recommended_requirement_reference"] += int(recommended)
        counts["games_with_any_requirement_reference"] += int(minimum or recommended)
        counts["games_with_both_requirement_references"] += int(minimum and recommended)
    return counts
