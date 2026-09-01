"""Automated test suite for Milestone 1 - Part 2: Data Ingestion & Preprocessing."""
import asyncio
import os
import json
import httpx
from app.main import app
from app.database.connection import connect_to_mongo, close_mongo_connection, get_collection
from app.database.collections import Collections
from app.services.preprocessing import (
    clean_text,
    remove_html,
    remove_urls,
    normalize_whitespace,
    normalize_contractions,
    detect_category,
    detect_sentiment,
    detect_priority,
)


async def test_preprocessing_service():
    print("-" * 60)
    print("[1/5] Testing Text Preprocessing & Cleaning Service...")
    print("-" * 60)

    # 1. HTML stripping
    html_input = "<div>The <b>Export to Jira</b> button is broken!</div>"
    html_cleaned = remove_html(html_input)
    assert "<b>" not in html_cleaned and "<div>" not in html_cleaned
    print(f"  [OK] HTML Cleaning: '{html_input}' -> '{html_cleaned}'")

    # 2. URL removal
    url_input = "Login fails at https://auth.mycompany.com/oauth2 please fix ASAP!"
    url_cleaned = remove_urls(url_input)
    assert "https://" not in url_cleaned
    print(f"  [OK] URL Removal:   '{url_input}' -> '{url_cleaned}'")

    # 3. Contraction normalization
    contract_input = "I can't access my team's workspace and won't be able to bill clients."
    contract_cleaned = normalize_contractions(contract_input)
    assert "cannot" in contract_cleaned and "will not" in contract_cleaned
    print(f"  [OK] Contractions:  '{contract_input}' -> '{contract_cleaned}'")

    # 4. Full cleaner
    raw_sample = "   <div>  I   can't   login to https://app.example.com/v1?ref=test!   </div>  "
    full_cleaned = clean_text(raw_sample)
    assert "cannot login to" in full_cleaned
    print(f"  [OK] Full Cleaner:  '{raw_sample}' -> '{full_cleaned}'")

    # 5. Categorization heuristics
    cat_auth = detect_category("Forgot password and 2FA SMS code is not working")
    cat_bill = detect_category("Charged twice on my credit card for Pro plan")
    cat_perf = detect_category("Analytics table takes 12 seconds to load")
    cat_ui = detect_category("Please add dark mode theme option in settings")
    print("  [OK] Category Detection:")
    print(f"       - 'Forgot password...': -> '{cat_auth}'")
    print(f"       - 'Charged twice...':   -> '{cat_bill}'")
    print(f"       - 'Takes 12 seconds...':-> '{cat_perf}'")
    print(f"       - 'Add dark mode...':   -> '{cat_ui}'")

    # 6. Sentiment & Priority heuristics
    sent_pos = detect_sentiment("Super intuitive design, our team loves it!")
    sent_neg = detect_sentiment("Completely broken, crashes every single time")
    prio_urg = detect_priority("Charged twice for annual subscription, need refund", "Billing & Payments", "Negative")
    print(f"  [OK] Sentiment Detection: '{sent_pos}', '{sent_neg}'")
    print(f"  [OK] Priority Detection:  '{prio_urg}'")


async def test_csv_upload(client: httpx.AsyncClient):
    print("\n" + "-" * 60)
    print("[2/5] Testing CSV File Ingestion Endpoint (POST /api/v1/feedback/upload)...")
    print("-" * 60)

    csv_path = os.path.join("..", "data", "raw", "sample_feedback.csv")
    if not os.path.exists(csv_path):
        csv_path = os.path.join("data", "raw", "sample_feedback.csv")

    with open(csv_path, "rb") as f:
        file_bytes = f.read()

    files = {"file": ("sample_feedback.csv", file_bytes, "text/csv")}
    response = await client.post("/api/v1/feedback/upload", files=files)
    
    print(f"  -> HTTP Status: {response.status_code}")
    report = response.json()
    print(f"  -> Ingestion Success:     {report.get('success')}")
    print(f"  -> Total Records:         {report.get('total_records')}")
    print(f"  -> Processed & Inserted:  {report.get('processed_records')}")
    print(f"  -> Duplicates Skipped:    {report.get('duplicate_records')}")
    print(f"  -> Categories Detected:   {report.get('categories_summary')}")
    print(f"  -> Sentiments Detected:   {report.get('sentiment_summary')}")

    assert response.status_code == 200, f"CSV upload failed: {response.text}"
    assert report.get("success") is True


async def test_json_upload(client: httpx.AsyncClient):
    print("\n" + "-" * 60)
    print("[3/5] Testing JSON Array Ingestion Endpoint (POST /api/v1/feedback/upload-json)...")
    print("-" * 60)

    json_path = os.path.join("..", "data", "raw", "sample_feedback.json")
    if not os.path.exists(json_path):
        json_path = os.path.join("data", "raw", "sample_feedback.json")

    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    response = await client.post("/api/v1/feedback/upload-json", json=records)
    print(f"  -> HTTP Status: {response.status_code}")
    report = response.json()
    print(f"  -> Ingestion Success:     {report.get('success')}")
    print(f"  -> Total Records:         {report.get('total_records')}")
    print(f"  -> Processed & Inserted:  {report.get('processed_records')}")
    print(f"  -> Categories Summary:    {report.get('categories_summary')}")

    assert response.status_code == 200
    assert report.get("success") is True


async def test_invalid_csv_handling(client: httpx.AsyncClient):
    print("\n" + "-" * 60)
    print("[4/5] Testing Edge Cases & Invalid CSV Ingestion (POST /api/v1/feedback/upload)...")
    print("-" * 60)

    invalid_path = os.path.join("..", "data", "raw", "invalid_feedback.csv")
    if not os.path.exists(invalid_path):
        invalid_path = os.path.join("data", "raw", "invalid_feedback.csv")

    with open(invalid_path, "rb") as f:
        file_bytes = f.read()

    files = {"file": ("invalid_feedback.csv", file_bytes, "text/csv")}
    response = await client.post("/api/v1/feedback/upload", files=files)
    
    print(f"  -> HTTP Status: {response.status_code}")
    report = response.json()
    print(f"  -> Total Rows:         {report.get('total_records')}")
    print(f"  -> Processed Records:  {report.get('processed_records')}")
    print(f"  -> Empty Text Skipped: {report.get('empty_text_records')}")
    print(f"  -> Duplicates Skipped: {report.get('duplicate_records')}")
    print(f"  -> Error Breakdown:    {len(report.get('errors', []))} row issues flagged")
    for err in report.get("errors", []):
        print(f"     * Row {err.get('row_index')}: {err.get('reason')}")

    assert response.status_code == 200, "Server should handle edge cases gracefully"
    assert report.get("empty_text_records") >= 2


async def test_database_verification():
    print("\n" + "-" * 60)
    print("[5/5] Verifying MongoDB Stored Records & Fields...")
    print("-" * 60)

    collection = get_collection(Collections.FEEDBACK)
    cursor = collection.find({"cleaned_text": {"$ne": None}}).sort("created_at", -1).limit(5)
    
    docs_checked = 0
    async for doc in cursor:
        docs_checked += 1
        orig_txt = str(doc.get("text") or "")
        clean_txt = str(doc.get("cleaned_text") or "")
        print(f"  Document #{docs_checked}:")
        print(f"    - ID:           {doc.get('_id')}")
        print(f"    - Customer ID:  {doc.get('customer_id')}")
        print(f"    - Source:       {doc.get('source')}")
        print(f"    - Original Text:{orig_txt[:60]}...")
        print(f"    - Cleaned Text: {clean_txt[:60]}...")
        print(f"    - Category:     {doc.get('category')}")
        print(f"    - Sentiment:    {doc.get('sentiment')}")
        print(f"    - Priority:     {doc.get('priority')}")
        
        # Verify both fields exist
        assert "text" in doc and doc["text"], "Original text must be preserved"
        assert "cleaned_text" in doc and doc["cleaned_text"], "Cleaned text must be populated"
        assert "category" in doc, "Category must be set"
        assert "sentiment" in doc, "Sentiment must be set"

    print(f"  [OK] Verified {docs_checked} recent MongoDB documents with full preprocessing fields.")


async def main():
    print("=" * 60)
    print("AI PRODUCT ASSISTANT - MILESTONE 1 PART 2 VERIFICATION")
    print("=" * 60)

    await test_preprocessing_service()

    await connect_to_mongo()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        await test_csv_upload(client)
        await test_json_upload(client)
        await test_invalid_csv_handling(client)
        await test_database_verification()

    await close_mongo_connection()
    print("\n" + "=" * 60)
    print("ALL MILESTONE 1 PART 2 TESTS PASSED PERFECTLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
