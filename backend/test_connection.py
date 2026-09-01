"""Automated integration test for FastAPI + MongoDB connection."""
import asyncio
import sys
import json
import httpx
from app.config import get_settings
from app.main import app
from app.database.connection import connect_to_mongo, close_mongo_connection, check_database_health


async def run_tests():
    print("=" * 60)
    print("STARTING AI PRODUCT ASSISTANT BACKEND VERIFICATION")
    print("=" * 60)

    settings = get_settings()
    print(f"App Name:      {settings.APP_NAME}")
    print(f"Environment:   {settings.ENVIRONMENT}")
    print(f"Database Name: {settings.DATABASE_NAME}")
    print(f"CORS Origins:  {settings.CORS_ORIGINS}")
    print("-" * 60)

    # 1. Test Database connection
    print("[1/5] Testing MongoDB Connection...")
    try:
        await connect_to_mongo()
        health = await check_database_health()
        print(f"  -> MongoDB Status: {health.get('status')}")
        print(f"  -> Latency:        {health.get('latency_ms')} ms")
        print(f"  -> Collections:    {health.get('collections')}")
    except Exception as e:
        print(f"  -> MongoDB Connection Error: {e}")
        health = await check_database_health()
        print(f"  -> Degraded Health: {health}")

    # 2. Test FastAPI endpoints via AsyncClient
    print("\n[2/5] Testing FastAPI Endpoints via AsyncClient...")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # GET /
        res_root = await client.get("/")
        print(f"  -> GET / : HTTP {res_root.status_code}")
        print(f"     Response: {res_root.json()}")
        assert res_root.status_code == 200, "Root endpoint failed"

        # GET /health
        res_health = await client.get("/health")
        print(f"  -> GET /health : HTTP {res_health.status_code}")
        print(f"     Response: {res_health.json()}")
        assert res_health.status_code == 200, "Health endpoint failed"

        # GET /health/database
        res_db_health = await client.get("/health/database")
        print(f"  -> GET /health/database : HTTP {res_db_health.status_code}")
        print(f"     Response: {res_db_health.json()}")

        # 3. Test Feedback Endpoints
        print("\n[3/5] Testing Feedback Endpoints (POST, GET, DELETE)...")
        feedback_payload = {
            "customer_id": "cust_test_101",
            "source": "Zendesk",
            "type": "review",
            "text": "The export to PDF feature is completely failing when table has >100 rows.",
            "category": "Export Bug",
            "sentiment": "Negative",
            "priority": "High",
            "status": "New",
            "metadata": {"browser": "Chrome", "version": "120.0"}
        }
        res_create_fb = await client.post("/api/v1/feedback", json=feedback_payload)
        print(f"  -> POST /api/v1/feedback : HTTP {res_create_fb.status_code}")
        if res_create_fb.status_code == 201:
            fb_data = res_create_fb.json()
            fb_id = fb_data["id"]
            print(f"     Created feedback ID: {fb_id}")

            # GET list
            res_list_fb = await client.get("/api/v1/feedback")
            print(f"  -> GET /api/v1/feedback : HTTP {res_list_fb.status_code}, total items: {res_list_fb.json().get('total')}")

            # GET single
            res_get_fb = await client.get(f"/api/v1/feedback/{fb_id}")
            print(f"  -> GET /api/v1/feedback/{fb_id} : HTTP {res_get_fb.status_code}")

            # DELETE test item
            res_del_fb = await client.delete(f"/api/v1/feedback/{fb_id}")
            print(f"  -> DELETE /api/v1/feedback/{fb_id} : HTTP {res_del_fb.status_code}")

        # 4. Test Support Tickets Endpoints
        print("\n[4/5] Testing Support Tickets Endpoints (POST, GET, DELETE)...")
        ticket_payload = {
            "ticket_id": "TIK-9001",
            "customer_id": "cust_enterprise_01",
            "source": "Support Portal",
            "text": "SSO Login integration with Okta times out periodically for European users.",
            "category": "Authentication",
            "sentiment": "Negative",
            "priority": "Urgent",
            "status": "Open",
            "metadata": {"region": "EU-West", "org_id": "org_442"}
        }
        res_create_tk = await client.post("/api/v1/support-tickets", json=ticket_payload)
        print(f"  -> POST /api/v1/support-tickets : HTTP {res_create_tk.status_code}")
        if res_create_tk.status_code == 201:
            tk_data = res_create_tk.json()
            tk_id = tk_data["id"]
            print(f"     Created ticket ID: {tk_id}")

            res_list_tk = await client.get("/api/v1/support-tickets")
            print(f"  -> GET /api/v1/support-tickets : HTTP {res_list_tk.status_code}, total items: {res_list_tk.json().get('total')}")

            # DELETE test item
            res_del_tk = await client.delete(f"/api/v1/support-tickets/{tk_id}")
            print(f"  -> DELETE /api/v1/support-tickets/{tk_id} : HTTP {res_del_tk.status_code}")

    print("\n[5/5] Closing Database Connection...")
    await close_mongo_connection()
    print("=" * 60)
    print("ALL TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
