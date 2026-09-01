"""Automated test suite for Milestone 1 - Part 3: Classification, Confidence, and Stats."""
import asyncio
import httpx
from app.main import app
from app.database.connection import connect_to_mongo, close_mongo_connection
from app.services.classification import classify_feedback, detect_sentiment, detect_priority, CATEGORIES


async def test_classifier_units():
    print("-" * 60)
    print("[1/4] Testing Classification & Confidence Scoring...")
    print("-" * 60)

    test_cases = [
        ("I cannot login with my Google SSO credentials on iOS", "Authentication", 0.75),
        ("The analytics page is extremely slow and times out after 10 seconds", "Performance", 0.75),
        ("We were charged twice on Stripe for the annual Pro subscription", "Payment", 0.75),
        ("The entire application crashes when clicking the export PDF button", "Bug", 0.70),
        ("The light gray text contrast makes the sidebar navigation unreadable", "UI/UX", 0.70),
        ("Please add automated sprint summary reports and custom estimation scales", "Feature Request", 0.70),
        ("Push notifications for mentions in user stories are delayed 30 mins", "Notifications", 0.70),
        ("Want to transfer organization workspace ownership before leaving company", "Account Management", 0.70),
        ("Would love to see Figma and Notion integrations supported", "Integration", 0.70),
        ("Just saying hello to the support team", "Other", 0.20),
    ]

    for text, expected_cat, min_conf in test_cases:
        cat, conf = classify_feedback(text)
        print(f"  [OK] '{text[:45]}...' -> Cat: '{cat}', Conf: {conf}")
        assert cat == expected_cat, f"Expected {expected_cat}, got {cat} for '{text}'"
        assert conf >= min_conf, f"Expected conf >= {min_conf}, got {conf}"


async def test_stats_and_categories_endpoints(client: httpx.AsyncClient):
    print("\n" + "-" * 60)
    print("[2/4] Testing Stats & Categories Endpoints...")
    print("-" * 60)

    # 1. Categories
    res_cats = await client.get("/api/v1/feedback/categories")
    print(f"  -> GET /api/v1/feedback/categories : HTTP {res_cats.status_code}")
    assert res_cats.status_code == 200
    categories = res_cats.json()
    assert len(categories) == len(CATEGORIES)
    print(f"     Found {len(categories)} controlled categories.")

    # 2. Stats
    res_stats = await client.get("/api/v1/feedback/stats")
    print(f"  -> GET /api/v1/feedback/stats : HTTP {res_stats.status_code}")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    print(f"     Total Records in DB:    {stats.get('total')}")
    print(f"     Category Distribution:  {stats.get('categories')}")
    print(f"     Sentiment Breakdown:    {stats.get('sentiment')}")
    print(f"     Priority Breakdown:     {stats.get('priority')}")
    print(f"     Average Confidence:     {stats.get('average_confidence')}")
    print(f"     Negative %:             {stats.get('negative_percentage')}%")
    print(f"     High/Urgent Priority %: {stats.get('high_priority_percentage')}%")


async def test_search_and_filter(client: httpx.AsyncClient):
    print("\n" + "-" * 60)
    print("[3/4] Testing Feedback Multi-Filter & Search Query...")
    print("-" * 60)

    # Search keyword
    res_search = await client.get("/api/v1/feedback?search=login")
    print(f"  -> GET /api/v1/feedback?search=login : HTTP {res_search.status_code}, items: {len(res_search.json().get('items', []))}")
    assert res_search.status_code == 200

    # Filter by category
    res_filter = await client.get("/api/v1/feedback?category=Authentication")
    print(f"  -> GET /api/v1/feedback?category=Authentication : HTTP {res_filter.status_code}, items: {len(res_filter.json().get('items', []))}")
    assert res_filter.status_code == 200

    # Filter by sentiment
    res_sent = await client.get("/api/v1/feedback?sentiment=Negative")
    print(f"  -> GET /api/v1/feedback?sentiment=Negative : HTTP {res_sent.status_code}, items: {len(res_sent.json().get('items', []))}")
    assert res_sent.status_code == 200


async def main():
    print("=" * 60)
    print("AI PRODUCT ASSISTANT - MILESTONE 1 PART 3 BACKEND VERIFICATION")
    print("=" * 60)

    await test_classifier_units()

    await connect_to_mongo()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await test_stats_and_categories_endpoints(client)
        await test_search_and_filter(client)

    await close_mongo_connection()
    print("\n" + "=" * 60)
    print("ALL PART 3 BACKEND TESTS PASSED PERFECTLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
