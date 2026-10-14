"""
Dry-run the demo CSV through the real services, with no database writes.

Loads the CSV the same way the importer does, classifies every row with the real
categorize()/detect_sentiment(), then runs the real theme, pain-point and feature
cluster extractors - so the demo screens can be checked before anything is imported.
"""

import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from services.categorization import categorize, detect_sentiment
from services.data_cleaning import clean_text
import asyncio
from services.clustering import cluster_feature_requests, count_unique_requesters
from services.text_mining import REQUEST_MARKERS, record_text
from services.theme_extraction import (
    extract_pain_points_from_feedback,
    extract_themes_from_feedback,
)
from services.trend_analysis import calculate_health_score

CSV_PATH = (
    sys.argv[1] if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "MunchMate_500_reviews.csv")
)


def load():
    records = []
    with open(CSV_PATH, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            title = (row.get("title") or "").strip()
            content = (row.get("content") or "").strip()
            text = f"{title} {content}".strip()
            rating = int(float(row.get("rating") or 0)) or None
            records.append({
                "title": title,
                "content": content,
                "rating": rating,
                "source": (row.get("source") or "").strip(),
                "customer_name": (row.get("customer_name") or "").strip(),
                "customer_email": (row.get("customer_email") or "").strip(),
                "category": categorize(text),
                "sentiment": detect_sentiment(text, rating),
            })
    return records


def bar(count, total, width=24):
    filled = round(width * count / max(total, 1))
    return "#" * filled + "." * (width - filled)


def main():
    records = load()
    total = len(records)

    cleaned = [asyncio.run(clean_text(str(r["content"]))) for r in records]
    unique_after_clean = len(set(cleaned))
    print(f"rows: {total}")
    print(f"rows surviving 'Clean text' dedupe: {unique_after_clean} "
          f"(would be deleted: {total - unique_after_clean})")
    print(f"unique customers: {len({r['customer_email'] for r in records})}")
    dupes = Counter(cleaned)
    print("most repeated content:")
    for text, count in dupes.most_common(5):
        print(f"  x{count}  {text[:70]}")
    print(f"health score: {calculate_health_score(records)}")

    for field in ("category", "sentiment", "source"):
        print(f"\n{field}:")
        counts = Counter(r[field] for r in records)
        for key, value in counts.most_common():
            print(f"  {key:<20} {value:>4}  {value / total * 100:5.1f}%  {bar(value, total)}")

    print("\nratings:")
    for key, value in sorted(Counter(r["rating"] for r in records).items()):
        print(f"  {key} star{'s' if key != 1 else ' ':<2} {value:>4}  {bar(value, total)}")

    print("\n" + "=" * 78)
    print("THEMES")
    print("=" * 78)
    for theme in extract_themes_from_feedback(records):
        split = theme.get("sentiment_breakdown") or {}
        print(f"  {theme['frequency']:>4}  {theme['title']:<26} "
              f"(+{split.get('positive', 0)}/-{split.get('negative', 0)})  "
              f"kw: {', '.join((theme.get('keywords') or [])[:5])}")

    print("\n" + "=" * 78)
    print("PAIN POINTS")
    print("=" * 78)
    for pain in extract_pain_points_from_feedback(records):
        print(f"  {pain['impact_score']:>5}/100  {pain['title']:<24} {pain['severity']:<7} "
              f"n={pain['affected_users_count']:<4} avg={pain['score_breakdown']['avg_rating']:<4} "
              f"neg={pain['score_breakdown']['negative_sentiment_pct']}% "
              f"bugs={pain['score_breakdown']['bug_count']}")
        print(f"          kw: {', '.join((pain.get('keywords') or [])[:6])}")
        print(f"          quote: {(pain.get('sample_quotes') or [''])[0][:95]}")

    print("\n" + "=" * 78)
    print("FEATURE CLUSTERS")
    print("=" * 78)
    for cluster in cluster_feature_requests(records):
        print(f"  {cluster['priority_score']:>5}  {cluster['cluster_name']:<26} "
              f"req={cluster['request_count']:<4} unique={cluster['unique_customers_count']:<4} "
              f"({cluster.get('unique_customers_count_basis')})  {cluster['demand_level']}")
        print(f"          kw: {', '.join((cluster.get('keywords') or [])[:6])}")

    print("\n" + "=" * 78)
    print("CHECKS")
    print("=" * 78)
    feature_rows = [r for r in records if any(m in record_text(r) for m in REQUEST_MARKERS)]
    print(f"request-marker rows feeding clustering: {len(feature_rows)}")
    print(f"distinct requesters in that set: {count_unique_requesters(feature_rows)}")

    complaints = [r for r in records if r["category"] in ("bug_report", "performance_issue")]
    praised = [r for r in complaints if r["rating"] >= 4]
    print(f"praise rows that carry defect vocabulary (keep this small): {len(praised)}")
    for row in praised[:6]:
        print(f"    - {row['rating']}star {row['title']} | {row['content'][:90]}")

    angry_asks = [r for r in records if r["category"] == "feature_request" and r["rating"] <= 2]
    print(f"low rated feature requests (asks from unhappy users): {len(angry_asks)}")
    for row in angry_asks[:6]:
        print(f"    - {row['rating']}star {row['title']} | {row['content'][:90]}")


if __name__ == "__main__":
    main()
