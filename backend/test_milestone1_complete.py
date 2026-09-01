"""Master End-to-End Verification Suite for Milestone 1 with Authentication Context.

Tests:
1. Health & Database Connection
2. Text Preprocessing & Cleaning
3. Controlled 10-Domain Classification & Confidence Scoring
4. Customer Feedback Ingestion (CSV & JSON) + Queries & Stats
5. Support Tickets Ingestion (CSV & JSON) + Queries & Stats
6. Error Resilience & Quality Edge Cases
"""
import asyncio
import os
import httpx

from app.main import app
from app.database.connection import connect_to_mongo, close_mongo_connection, get_collection
from app.database.collections import Collections
from app.services.preprocessing import clean_text
from app.services.classification import (
    classify_feedback,
    detect_sentiment,
    detect_priority,
    CATEGORIES,
)

RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


async def test_health_and_database(client: httpx.AsyncClient):
    print("\n" + "=" * 65)
    print("[1/6] TESTING HEALTH & DATABASE CONNECTIVITY")
    print("=" * 65)

    res_root = await client.get("/")
    assert res_root.status_code == 200, f"Expected 200, got {res_root.status_code}"
    print(f"  [PASS] GET / -> HTTP 200 (App: {res_root.json().get('app_name')})")

    res_health = await client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json().get("status") == "healthy"
    print("  [PASS] GET /health -> HTTP 200 (Status: healthy)")

    res_db = await client.get("/health/database")
    assert res_db.status_code == 200
    db_data = res_db.json()
    assert db_data.get("database") == "connected"
    print(f"  [PASS] GET /health/database -> HTTP 200 (DB: {db_data.get('database_name')}, Latency: {db_data.get('latency_ms')}ms)")


def test_preprocessing():
    print("\n" + "=" * 65)
    print("[2/6] TESTING TEXT PREPROCESSING & CLEANING")
    print("=" * 65)

    raw_input = "  <div>I can't access https://app.example.com/login?token=abc! Contact user@test.com  </div> "
    cleaned = clean_text(raw_input)
    print(f"  Raw:     '{raw_input}'")
    print(f"  Cleaned: '{cleaned}'")

    assert "<div>" not in cleaned
    assert "https://" not in cleaned
    assert "user@test.com" not in cleaned
    assert "cannot" in cleaned
    print("  [PASS] HTML stripped, contractions expanded, emails removed, whitespace normalized.")


def test_classification():
    print("\n" + "=" * 65)
    print("[3/6] TESTING 10-DOMAIN CLASSIFICATION ENGINE")
    print("=" * 65)

    test_matrix = [
        ("Unable to login with Google SSO, SAML error 500", "Authentication", 0.75),
        ("Dashboard takes 12 seconds to load analytics table", "Performance", 0.75),
        ("Charged twice on Stripe credit card invoice", "Payment", 0.75),
        ("Button is misaligned and hard to click on mobile", "UI/UX", 0.70),
        ("App crashes with unhandled exception on export", "Bug", 0.75),
        ("Would love to see Figma and Notion integrations supported", "Integration", 0.70),
        ("Just a general note to the team", "Other", 0.20),
    ]

    for text, expected_cat, min_conf in test_matrix:
        cat, conf = classify_feedback(text)
        print(f"  [PASS] '{text[:40]}...' -> Cat: '{cat}', Conf: {conf}")
        assert cat == expected_cat, f"Expected {expected_cat}, got {cat}"
        assert conf >= min_conf, f"Expected conf >= {min_conf}, got {conf}"

    assert detect_sentiment("Love this product! Amazing speed.") == "Positive"
    assert detect_sentiment("Completely broken and terrible error.") == "Negative"
    assert detect_priority("Urgent: charged twice on credit card") == "Urgent"
    print("  [PASS] Sentiment & Priority heuristics verified.")


async def test_feedback_pipeline(client: httpx.AsyncClient, headers: dict):
    print("\n" + "=" * 65)
    print("[4/6] TESTING FEEDBACK INGESTION, QUERIES & STATS")
    print("=" * 65)

    # 1. Categories
    res_cats = await client.get("/api/v1/feedback/categories", headers=headers)
    assert res_cats.status_code == 200
    categories = res_cats.json()
    assert len(categories) == len(CATEGORIES)
    print(f"  [PASS] GET /api/v1/feedback/categories -> 10 controlled categories returned.")

    # 2. Stats
    res_stats = await client.get("/api/v1/feedback/stats", headers=headers)
    assert res_stats.status_code == 200
    stats = res_stats.json()
    print(f"  [PASS] GET /api/v1/feedback/stats -> Total feedback in DB: {stats.get('total')}")

    # 3. CSV Ingestion
    csv_path = os.path.join(RAW_DATA_DIR, "sample_feedback.csv")
    with open(csv_path, "rb") as f:
        files = {"file": ("sample_feedback.csv", f, "text/csv")}
        res_upload = await client.post("/api/v1/feedback/upload", headers=headers, files=files)
    assert res_upload.status_code == 200
    report = res_upload.json()
    assert report.get("success") is True
    print(f"  [PASS] POST /api/v1/feedback/upload -> Processed: {report.get('processed_records')}, Duplicates: {report.get('duplicate_records')}")

    # 4. JSON Ingestion
    json_payload = [
        {
            "customer_id": "CUST-LIVE-1",
            "source": "Zendesk",
            "text": "Live test feedback: Great dashboard UI, love the speed!",
        }
    ]
    res_json = await client.post("/api/v1/feedback/upload-json", headers=headers, json=json_payload)
    assert res_json.status_code == 200
    print(f"  [PASS] POST /api/v1/feedback/upload-json -> Success: {res_json.json().get('success')}")

    # 5. Search & Filter
    res_search = await client.get("/api/v1/feedback?search=dashboard", headers=headers)
    assert res_search.status_code == 200
    print(f"  [PASS] GET /api/v1/feedback?search=dashboard -> Found {len(res_search.json().get('items', []))} matches.")


async def test_support_tickets_pipeline(client: httpx.AsyncClient, headers: dict):
    print("\n" + "=" * 65)
    print("[5/6] TESTING SUPPORT TICKETS INGESTION, QUERIES & STATS")
    print("=" * 65)

    # 1. Upload Support Tickets CSV
    ticket_csv_path = os.path.join(RAW_DATA_DIR, "sample_support_tickets.csv")
    with open(ticket_csv_path, "rb") as f:
        files = {"file": ("sample_support_tickets.csv", f, "text/csv")}
        res_upload = await client.post("/api/v1/support-tickets/upload", headers=headers, files=files)
    assert res_upload.status_code == 200
    report = res_upload.json()
    assert report.get("success") is True
    print(f"  [PASS] POST /api/v1/support-tickets/upload -> Ingested {report.get('processed_records')} tickets (Duplicates: {report.get('duplicate_records')}).")

    # 2. Upload JSON Support Tickets
    ticket_json_path = os.path.join(RAW_DATA_DIR, "sample_support_tickets.json")
    import json
    with open(ticket_json_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    res_json = await client.post("/api/v1/support-tickets/upload-json", headers=headers, json=records)
    assert res_json.status_code == 200
    print(f"  [PASS] POST /api/v1/support-tickets/upload-json -> Success: {res_json.json().get('success')}")

    # 3. List & Filter Support Tickets
    res_list = await client.get("/api/v1/support-tickets?page=1&page_size=10", headers=headers)
    assert res_list.status_code == 200
    tickets_data = res_list.json()
    print(f"  [PASS] GET /api/v1/support-tickets -> Total: {tickets_data.get('total')} tickets stored.")

    # 4. Support Ticket Stats
    res_stats = await client.get("/api/v1/support-tickets/stats", headers=headers)
    assert res_stats.status_code == 200
    print(f"  [PASS] GET /api/v1/support-tickets/stats -> Priorities: {res_stats.json().get('priority')}")


async def test_error_resilience(client: httpx.AsyncClient, headers: dict):
    print("\n" + "=" * 65)
    print("[6/6] TESTING ERROR HANDLING & RESILIENCE")
    print("=" * 65)

    # 1. Invalid File Type
    files = {"file": ("malicious.exe", b"invalid executable bytes", "application/octet-stream")}
    res_bad_file = await client.post("/api/v1/feedback/upload", headers=headers, files=files)
    assert res_bad_file.status_code == 400
    print(f"  [PASS] Uploading non-CSV rejected with HTTP 400.")

    # 2. Corrupted / Empty Text Rows
    invalid_csv_path = os.path.join(RAW_DATA_DIR, "invalid_feedback.csv")
    with open(invalid_csv_path, "rb") as f:
        files = {"file": ("invalid_feedback.csv", f, "text/csv")}
        res_invalid = await client.post("/api/v1/feedback/upload", headers=headers, files=files)
    assert res_invalid.status_code == 200
    inv_report = res_invalid.json()
    assert inv_report.get("empty_text_records") > 0 or inv_report.get("duplicate_records") > 0
    print(f"  [PASS] Handled invalid/empty rows safely. Flagged {len(inv_report.get('errors', []))} error notices.")

    # 3. Non-existent ID Lookup
    res_404 = await client.get("/api/v1/feedback/60d5ec49f1b2c8a1d4f00000", headers=headers)
    assert res_404.status_code == 404
    print("  [PASS] Non-existent ID returned clean HTTP 404.")


async def main():
    print("=" * 65)
    print("AI PRODUCT ASSISTANT - MILESTONE 1 MASTER TEST SUITE")
    print("=" * 65)

    test_preprocessing()
    test_classification()

    await connect_to_mongo()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await test_health_and_database(client)

        # Authenticate test runner session
        test_email = "m1_test_runner@example.com"
        users_col = get_collection(Collections.USERS)
        await users_col.delete_many({"email": test_email})

        reg_res = await client.post("/api/v1/auth/register", json={
            "name": "M1 Test Runner",
            "email": test_email,
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
            "workspace_name": "Milestone 1 Workspace",
        })
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        await test_feedback_pipeline(client, headers)
        await test_support_tickets_pipeline(client, headers)
        await test_error_resilience(client, headers)

        # Cleanup
        await users_col.delete_many({"email": test_email})

    await close_mongo_connection()
    print("\n" + "=" * 65)
    print("ALL MILESTONE 1 INTEGRATION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
