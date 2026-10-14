"""
Engine accuracy audit — read-only.

Compares the analysis stored for a workspace against what the current engines produce
from the same feedback, and measures the two things the earlier output got wrong: how
many "different" pain points described the same records, and whether the priority inputs
were measured or invented.

Nothing here writes: it opens the database, reads, runs the deterministic engines and
prints. Use it after changing a mining engine to see the effect on real corpora.

    python tools/_engine_audit.py <workspace_id>
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database  # noqa: E402
from database import db  # noqa: E402
from routers.insights import _identify_topics  # noqa: E402
from services.clustering import cluster_feature_requests  # noqa: E402
from services.prioritization_service import measured_priority_inputs  # noqa: E402
from services.text_mining import match_records_by_terms  # noqa: E402
from services.theme_extraction import (  # noqa: E402
    extract_pain_points_from_feedback,
    extract_themes_from_feedback,
)


def _record_text(item):
    return f"{item.get('title') or ''} {item.get('content') or ''}".lower()


def _substring_members(topics, records):
    """Membership under the rule the older analysis used: any keyword as a substring."""
    members = set()
    for topic in topics:
        terms = [str(term).lower() for term in (topic.get("keywords") or [])]
        terms += re.findall(r"[a-z]{4,}", str(topic.get("title") or topic.get("cluster_name") or "").lower())
        for index, record in enumerate(records):
            text = _record_text(record)
            if any(term and term in text for term in terms):
                members.add(index)
    return members


def _whole_word_members(topics, records):
    """Membership under the current rule: whole-word mentions of the topic's own terms."""
    members = set()
    index_by_id = {id(record): index for index, record in enumerate(records)}
    for topic in topics:
        terms = [str(term).lower() for term in (topic.get("keywords") or [])][:6]
        terms += re.findall(r"[a-z]{4,}", str(topic.get("title") or topic.get("cluster_name") or "").lower())
        if not terms:
            continue
        for record in match_records_by_terms(records, terms):
            members.add(index_by_id[id(record)])
    return members


def _pairwise_overlap(topics, records, member_fn):
    """
    How much any two topics describe the same records.

    Summing claimed volume against a union of matched records hides this: groups that are
    disjoint but each cover many records look harmless, while the question a reviewer asks
    is whether two *topics* are the same issue. Pairwise containment answers that.
    """
    members = [set(member_fn([topic], records)) for topic in topics]

    pairs = 0
    merged = 0
    worst = 0.0
    details = []
    for first in range(len(members)):
        for second in range(first + 1, len(members)):
            if not members[first] or not members[second]:
                continue
            pairs += 1
            containment = len(members[first] & members[second]) / min(len(members[first]), len(members[second]))
            if containment >= 0.6:
                merged += 1
                details.append((topics[first], topics[second], round(containment, 2)))
            worst = max(worst, containment)
    return {"pairs": pairs, "near_duplicates": merged, "worst_containment": round(worst, 2), "details": details}


def _report(name, topics, records, member_fn):
    claimed = sum(int(topic.get("affected_users_count") or topic.get("request_count") or 0) for topic in topics)
    print(f"  {name}: {len(topics)} topic(s), claimed volume {claimed}")
    overlap = _pairwise_overlap(topics, records, member_fn)
    print(f"    topic pairs compared: {overlap['pairs']}; pairs that are the same records: "
          f"{overlap['near_duplicates']}; worst containment: {overlap['worst_containment']}")
    # The rule the hygiene pass enforces: no kept topic may have 80% of its own records
    # already claimed by a higher-ranked topic.
    claimed_so_far = set()
    violations = 0
    worst = 0.0
    for topic in topics:
        own = set(member_fn([topic], records))
        if own:
            share = len(own & claimed_so_far) / len(own)
            worst = max(worst, share)
            if share >= 0.8:
                violations += 1
        claimed_so_far |= own
    print(f"    duplicates the hygiene rule forbids (>=80% already claimed): {violations}"
          f"; worst share of a higher-ranked topic's records: {round(worst, 2)}")
    for first, second, containment in overlap["details"][:4]:
        first_label = first.get("title") or first.get("cluster_name")
        second_label = second.get("title") or second.get("cluster_name")
        print(f"      {containment:.2f} | {first_label} ~ {second_label}")
    return overlap


async def audit(workspace_id: str):
    await database.connect_to_mongo()
    records = await db.feedback.find({"workspace_id": workspace_id}).to_list(length=None)
    stored = await db.workspace_insights.find_one({"workspace_id": workspace_id})
    print(f"workspace {workspace_id}: {len(records)} feedback records, "
          f"analysis stored={'yes' if stored else 'no'}")
    if not records:
        return

    if stored:
        print("\nSTORED ANALYSIS (as produced earlier)")
        print(f"  model: {stored.get('ai_model')} at {stored.get('analyzed_at')}")
        print("  pain points:")
        for point in stored.get("pain_points") or []:
            print(f"    {point.get('id')} | {point.get('title')} | n={point.get('affected_users_count')}"
                  f" | impact {point.get('impact_score')}")
        _report("stored pain points", stored.get("pain_points") or [], records, _substring_members)
        print("  clusters:")
        for cluster in stored.get("feature_clusters") or []:
            print(f"    {cluster.get('id')} | {cluster.get('cluster_name')} | req={cluster.get('request_count')}")
        _report("stored clusters", stored.get("feature_clusters") or [], records, _substring_members)

    print("\nCURRENT ENGINES (deterministic, no AI, same corpus)")
    themes = extract_themes_from_feedback(records)
    pain_points = extract_pain_points_from_feedback(records)
    clusters = cluster_feature_requests(records)

    print("  themes:", ", ".join(theme["title"] for theme in themes) or "none")
    print("  pain points:")
    for point in pain_points:
        print(f"    {point['id']} | {point['title']} | rank {point['rank']} | n={point['affected_users_count']}"
              f" | impact {point['impact_score']} | {point['severity']}"
              f" | avg {point['score_breakdown'].get('avg_rating')}"
              f" | {point['score_breakdown'].get('negative_sentiment_pct')}% negative")
    _report("mined pain points", pain_points, records, _whole_word_members)
    print("  clusters:")
    for cluster in clusters:
        print(f"    {cluster['id']} | {cluster['cluster_name']} | rank {cluster['rank']}"
              f" | req={cluster['request_count']} | {cluster['demand_level']}")
    _report("mined clusters", clusters, records, _whole_word_members)

    # The analyze flow runs this hygiene step for both the mined and the AI-grounded paths.
    print("\nAFTER TOPIC HYGIENE (what a re-analysis would now store)")
    merged_points = _identify_topics(pain_points, records, "pain_point")
    merged_clusters = _identify_topics(clusters, records, "cluster")
    for point in merged_points:
        aliases = point.get("also_described_as") or []
        print(f"    {point['id']} | {point['title']} | rank {point['rank']} | n={point['affected_users_count']}"
              f" | impact {point['impact_score']}" + (f" | also described as: {', '.join(aliases)}" if aliases else ""))
    _report("pain points after hygiene", merged_points, records, _whole_word_members)
    for cluster in merged_clusters:
        aliases = cluster.get("also_described_as") or []
        print(f"    {cluster['id']} | {cluster['cluster_name']} | rank {cluster['rank']}"
              f" | req={cluster['request_count']}" + (f" | also described as: {', '.join(aliases)}" if aliases else ""))
    _report("clusters after hygiene", merged_clusters, records, _whole_word_members)

    print("\nSTABILITY: ids must survive a second run of the same corpus")
    repeat = extract_pain_points_from_feedback(list(reversed(records)))
    print(f"  pain point ids identical across runs: "
          f"{[p['id'] for p in pain_points] == [p['id'] for p in repeat]}")

    print("\nSEEDED PRIORITY INPUTS (measured vs assumed)")
    for topic, kind in [(point, "pain_point") for point in pain_points[:6]] + \
                       [(cluster, "cluster") for cluster in clusters[:6]]:
        count = int(topic.get("affected_users_count") or topic.get("request_count") or 0)
        urgency = topic.get("severity") or topic.get("demand_level") or "medium"
        inputs = measured_priority_inputs(count, urgency)
        rice = round(inputs["reach"] * inputs["impact"] * inputs["confidence"] / inputs["effort"], 1)
        label = topic.get("title") or topic.get("cluster_name")
        print(f"  {kind:10s} {label[:34]:36s} records={count:5d} urgency={urgency:6s} "
              f"reach={inputs['reach']:.0f} impact={inputs['impact']} conf={inputs['confidence']} "
              f"effort={inputs['effort']} moscow={inputs['moscow']:11s} RICE={rice}")

    must_have = sum(1 for topic in pain_points + clusters
                    if measured_priority_inputs(int(topic.get("affected_users_count") or topic.get("request_count") or 0),
                                               topic.get("severity") or topic.get("demand_level") or "medium")["moscow"] == "must_have")
    total = len(pain_points) + len(clusters)
    print(f"  must-have items: {must_have} of {total}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python tools/_engine_audit.py <workspace_id>")
        raise SystemExit(1)
    asyncio.run(audit(sys.argv[1]))
