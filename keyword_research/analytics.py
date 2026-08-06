"""
Keyword Research module: analytics.

Purpose of this file
--------------------
Everything here is plain Python operating on an already-deduped keyword
list (either one batch's own list, or the cross-batch master list from
`database.load_master_keywords`) -- no LLM judgment, fully reproducible
for the same input, same philosophy as content_agent/qa_checks.py. These
are the four report views Rahul asked for: competitor overlap, opportunity
keywords, trending keywords, and a per-competitor summary.

A note on the "opportunity keywords" thresholds
------------------------------------------------
Rahul asked for sensible defaults rather than specific numbers (2026-08-06):
top third of keywords by search volume AND bottom third by difficulty,
computed from whatever data is actually in front of it (percentile-based,
not a fixed number) -- so it adapts to Simprosys's own niche instead of
assuming a specific difficulty scale. Easy to swap for exact thresholds
later if Rahul decides he wants them.
"""

import math

DEFAULT_OPPORTUNITY_FRACTION = 1 / 3
DEFAULT_TOP_N = 20


def _numeric_values(keywords, field):
    return [k[field] for k in keywords if isinstance(k.get(field), (int, float))]


def _percentile(values, fraction):
    """Linear-interpolation percentile, no numpy dependency needed for
    just this one calculation."""
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[int(index)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def compute_opportunity_keywords(keywords, top_fraction=DEFAULT_OPPORTUNITY_FRACTION):
    """
    High search volume AND low difficulty -- the keywords worth
    prioritizing first. Thresholds are percentile-based against the
    keyword set actually passed in (see module docstring), so this
    adapts whether it's run against one batch or the full master list.
    """
    volumes = _numeric_values(keywords, "avg_monthly_search_volume")
    difficulties = _numeric_values(keywords, "difficulty")
    if not volumes or not difficulties:
        return []

    volume_threshold = _percentile(volumes, 1 - top_fraction)
    difficulty_threshold = _percentile(difficulties, top_fraction)

    opportunities = [
        keyword for keyword in keywords
        if isinstance(keyword.get("avg_monthly_search_volume"), (int, float))
        and isinstance(keyword.get("difficulty"), (int, float))
        and keyword["avg_monthly_search_volume"] >= volume_threshold
        and keyword["difficulty"] <= difficulty_threshold
    ]
    return sorted(opportunities, key=lambda k: k["avg_monthly_search_volume"], reverse=True)


def compute_trending_keywords(keywords, top_n=DEFAULT_TOP_N):
    """Biggest positive and negative year-over-year movers. Keywords with
    no yoy_change value are excluded (nothing to rank them by)."""
    with_yoy = [k for k in keywords if isinstance(k.get("yoy_change"), (int, float))]
    rising = sorted([k for k in with_yoy if k["yoy_change"] > 0], key=lambda k: k["yoy_change"], reverse=True)
    declining = sorted([k for k in with_yoy if k["yoy_change"] < 0], key=lambda k: k["yoy_change"])
    return {"rising": rising[:top_n], "declining": declining[:top_n]}


def compute_competitor_overlap(keywords, top_n=DEFAULT_TOP_N):
    """
    Which keywords are contested by the most competitors (highest overlap
    -- everyone's targeting these) versus keywords only one competitor
    has found (potential content gaps for the others). Sorted by how many
    competitors share the keyword, descending.
    """
    contested = sorted(
        ({**keyword, "competitor_count": len(keyword["competitors"])} for keyword in keywords),
        key=lambda k: k["competitor_count"],
        reverse=True,
    )
    return {
        "most_contested": [k for k in contested if k["competitor_count"] > 1][:top_n],
        "unique_to_one_competitor_count": sum(1 for k in contested if k["competitor_count"] == 1),
    }


def compute_per_competitor_summary(keywords):
    """One row per competitor: how many keywords they show up in, how many
    of those are exclusively theirs (no other competitor has them), and
    their average volume/difficulty across those keywords."""
    by_competitor = {}
    for keyword in keywords:
        is_unique = len(keyword["competitors"]) == 1
        for competitor in keyword["competitors"]:
            stats = by_competitor.setdefault(competitor, {
                "competitor": competitor, "keyword_count": 0, "unique_keyword_count": 0,
                "_volumes": [], "_difficulties": [],
            })
            stats["keyword_count"] += 1
            if is_unique:
                stats["unique_keyword_count"] += 1
            if isinstance(keyword.get("avg_monthly_search_volume"), (int, float)):
                stats["_volumes"].append(keyword["avg_monthly_search_volume"])
            if isinstance(keyword.get("difficulty"), (int, float)):
                stats["_difficulties"].append(keyword["difficulty"])

    summary = []
    for stats in by_competitor.values():
        volumes = stats.pop("_volumes")
        difficulties = stats.pop("_difficulties")
        stats["avg_volume"] = round(sum(volumes) / len(volumes), 1) if volumes else None
        stats["avg_difficulty"] = round(sum(difficulties) / len(difficulties), 1) if difficulties else None
        summary.append(stats)

    return sorted(summary, key=lambda s: s["keyword_count"], reverse=True)


def run_all_analytics(keywords):
    """Everything bundled together, the shape the dashboard page and PDF
    generators actually want."""
    return {
        "total_keywords": len(keywords),
        "total_competitors": len({c for k in keywords for c in k["competitors"]}),
        "opportunity_keywords": compute_opportunity_keywords(keywords),
        "trending_keywords": compute_trending_keywords(keywords),
        "competitor_overlap": compute_competitor_overlap(keywords),
        "per_competitor_summary": compute_per_competitor_summary(keywords),
    }
