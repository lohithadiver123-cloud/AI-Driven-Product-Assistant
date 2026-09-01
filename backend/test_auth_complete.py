"""Master Automated Test Suite for Authentication, Authorization & Workspace Isolation."""
import asyncio
import os
import sys

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database.connection import connect_to_mongo, close_mongo_connection, get_collection
from app.database.collections import Collections
from app.services.email_service import dev_email_outbox


async def run_auth_test_suite():
    print("=" * 70)
    print("AI PRODUCT ASSISTANT -- AUTHENTICATION & RBAC TEST SUITE")
    print("=" * 70)

    await connect_to_mongo()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # Clean test accounts if present
        users_col = get_collection(Collections.USERS)
        workspaces_col = get_collection(Collections.WORKSPACES)
        refresh_col = get_collection(Collections.REFRESH_TOKENS)
        reset_col = get_collection(Collections.PASSWORD_RESET_TOKENS)
        verify_col = get_collection(Collections.EMAIL_VERIFICATION_TOKENS)
        feedback_col = get_collection(Collections.FEEDBACK)

        test_email_a = "founder_test_a@example.com"
        test_email_b = "founder_test_b@example.com"

        await users_col.delete_many({"email": {"$in": [test_email_a, test_email_b]}})

        # -------------------------------------------------------------
        # Section 1: User Registration
        # -------------------------------------------------------------
        print("\n[SECTION 1] Testing Registration...")

        # 1.1 Password mismatch
        res = await client.post("/api/v1/auth/register", json={
            "name": "Alex Founder",
            "email": test_email_a,
            "password": "Password123",
            "confirm_password": "WrongPassword123",
            "workspace_name": "Acme SaaS",
        })
        assert res.status_code == 400, f"Expected 400 for mismatch, got {res.status_code}"
        print("  [OK] Password mismatch caught correctly (400)")

        # 1.2 Weak password (length < 8 or missing digits)
        res = await client.post("/api/v1/auth/register", json={
            "name": "Alex Founder",
            "email": test_email_a,
            "password": "weak",
            "confirm_password": "weak",
            "workspace_name": "Acme SaaS",
        })
        assert res.status_code in (400, 422), f"Expected 400/422 for weak password, got {res.status_code}"
        print("  [OK] Weak password rejected correctly (422/400)")

        # 1.3 Valid Registration
        res = await client.post("/api/v1/auth/register", json={
            "name": "Alex Founder",
            "email": test_email_a,
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
            "workspace_name": "Acme SaaS",
        })
        assert res.status_code == 201, f"Registration failed: {res.text}"
        data_a = res.json()
        token_a = data_a["access_token"]
        refresh_a = data_a["refresh_token"]
        ws_id_a = data_a["user"]["current_workspace_id"]
        assert token_a and refresh_a and ws_id_a
        assert data_a["user"]["role"] == "OWNER"
        print(f"  [OK] Valid user registered! User ID: {data_a['user']['id']}, Workspace: {data_a['user']['workspace_name']} (ID: {ws_id_a})")

        # 1.4 Duplicate Registration
        res = await client.post("/api/v1/auth/register", json={
            "name": "Alex Duplicate",
            "email": test_email_a,
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
        })
        assert res.status_code == 409, f"Expected 409 for duplicate, got {res.status_code}"
        print("  [OK] Duplicate email prevented correctly (409 Conflict)")

        # -------------------------------------------------------------
        # Section 2: Email Verification
        # -------------------------------------------------------------
        print("\n[SECTION 2] Testing Email Verification...")
        verify_doc = await verify_col.find_one({"user_id": data_a["user"]["id"], "used_at": None})
        assert verify_doc is not None, "Email verification token document not found"

        assert len(dev_email_outbox) > 0, "No emails in dev outbox"
        latest_email = dev_email_outbox[-1]
        assert latest_email["to"] == test_email_a
        assert latest_email["type"] == "VERIFICATION"
        verify_link = latest_email["link"]
        raw_verify_token = verify_link.split("token=")[-1]
        print(f"  [OK] Verification email captured in dev outbox with token: {raw_verify_token[:12]}...")

        # Test verification endpoint
        res = await client.post("/api/v1/auth/verify-email", json={"token": raw_verify_token})
        assert res.status_code == 200, f"Email verification failed: {res.text}"
        print("  [OK] Email verified successfully (200)")

        # Test single-use token consumption
        res = await client.post("/api/v1/auth/verify-email", json={"token": raw_verify_token})
        assert res.status_code == 400, "Expected 400 for already-used verification token"
        print("  [OK] Token is strictly single-use (400 on second try)")

        # -------------------------------------------------------------
        # Section 3: Login & Token Management
        # -------------------------------------------------------------
        print("\n[SECTION 3] Testing Login & Token Lifecycle...")

        # 3.1 Bad password
        res = await client.post("/api/v1/auth/login", json={
            "email": test_email_a,
            "password": "IncorrectPassword999",
        })
        assert res.status_code == 401, f"Expected 401 for bad password, got {res.status_code}"
        print("  [OK] Bad password rejected (401)")

        # 3.2 Valid login
        res = await client.post("/api/v1/auth/login", json={
            "email": test_email_a,
            "password": "SecurePassword123",
        })
        assert res.status_code == 200, f"Login failed: {res.text}"
        login_data = res.json()
        token_a = login_data["access_token"]
        refresh_a = login_data["refresh_token"]
        print("  [OK] Successful login! New JWT Access & Refresh token issued.")

        # 3.3 Get Current User Profile (GET /api/v1/auth/me)
        res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
        assert res.status_code == 200, f"GET /me failed: {res.text}"
        profile = res.json()
        assert profile["email"] == test_email_a
        assert profile["email_verified"] is True
        assert profile["current_workspace_id"] == ws_id_a
        print(f"  [OK] GET /auth/me verified: {profile['name']} ({profile['role']}) in workspace '{profile['workspace_name']}'")

        # 3.4 Refresh Token Rotation
        res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_a})
        assert res.status_code == 200, f"Refresh token failed: {res.text}"
        refresh_data = res.json()
        token_a_new = refresh_data["access_token"]
        refresh_a_new = refresh_data["refresh_token"]
        assert refresh_a_new != refresh_a, "Refresh token was not rotated!"
        print("  [OK] Refresh token rotation verified (old token revoked, new token issued).")

        # 3.5 Attempting to reuse the old refresh token should fail
        res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_a})
        assert res.status_code == 401, "Expected 401 on reused revoked refresh token"
        print("  [OK] Replay attack with revoked refresh token rejected (401)")

        token_a = token_a_new
        refresh_a = refresh_a_new

        # -------------------------------------------------------------
        # Section 4: Workspace Isolation & Data Scoping
        # -------------------------------------------------------------
        print("\n[SECTION 4] Testing Multi-Tenant Workspace Isolation...")

        # Register User B in a completely separate workspace
        res = await client.post("/api/v1/auth/register", json={
            "name": "Bella Founder",
            "email": test_email_b,
            "password": "SecurePassword456",
            "confirm_password": "SecurePassword456",
            "workspace_name": "Beta Workspace",
        })
        assert res.status_code == 201
        data_b = res.json()
        token_b = data_b["access_token"]
        ws_id_b = data_b["user"]["current_workspace_id"]
        assert ws_id_b != ws_id_a, "Workspace IDs must be distinct!"
        print(f"  [OK] User B registered in Workspace B: {ws_id_b}")

        # User A creates a feedback record in Workspace A
        res = await client.post(
            "/api/v1/feedback",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "customer_id": "CUST-A-1",
                "source": "Zendesk",
                "text": "User A exclusive feedback item: SAML 2.0 login issue.",
            },
        )
        assert res.status_code == 201, f"Create feedback failed: {res.text}"
        feedback_a_id = res.json()["id"]
        print(f"  [OK] User A created feedback item {feedback_a_id} in Workspace A")

        # User B lists feedback: must NOT see User A's feedback item!
        res = await client.get("/api/v1/feedback", headers={"Authorization": f"Bearer {token_b}"})
        assert res.status_code == 200
        items_b = res.json()["items"]
        b_item_ids = [item["id"] for item in items_b]
        assert feedback_a_id not in b_item_ids, "CRITICAL: Workspace isolation failure! User B saw User A's feedback!"
        print("  [OK] Workspace Isolation verified: User B cannot see Workspace A's feedback list.")

        # User B directly tries GET /feedback/{feedback_a_id} -> must return 404
        res = await client.get(f"/api/v1/feedback/{feedback_a_id}", headers={"Authorization": f"Bearer {token_b}"})
        assert res.status_code == 404, f"Expected 404 cross-tenant access denial, got {res.status_code}"
        print("  [OK] Direct ID tampering blocked: User B received 404 trying to read User A's record.")

        # -------------------------------------------------------------
        # Section 5: Password Reset Flow
        # -------------------------------------------------------------
        print("\n[SECTION 5] Testing Password Reset Flow...")

        # 5.1 Request password reset
        res = await client.post("/api/v1/auth/forgot-password", json={"email": test_email_a})
        assert res.status_code == 200, f"Forgot password failed: {res.text}"
        assert len(dev_email_outbox) > 0
        latest_email = dev_email_outbox[-1]
        assert latest_email["to"] == test_email_a
        assert latest_email["type"] == "PASSWORD_RESET"
        reset_link = latest_email["link"]
        raw_reset_token = reset_link.split("token=")[-1]
        print(f"  [OK] Password reset token generated & captured: {raw_reset_token[:12]}...")

        # 5.2 Reset Password
        res = await client.post("/api/v1/auth/reset-password", json={
            "token": raw_reset_token,
            "new_password": "NewBrandSecurePw999",
            "confirm_password": "NewBrandSecurePw999",
        })
        assert res.status_code == 200, f"Reset password failed: {res.text}"
        print("  [OK] Password reset confirmed (200)")

        # 5.3 Attempting to login with OLD password must fail
        res = await client.post("/api/v1/auth/login", json={
            "email": test_email_a,
            "password": "SecurePassword123",
        })
        assert res.status_code == 401
        print("  [OK] Old password invalid (401)")

        # 5.4 Login with NEW password succeeds
        res = await client.post("/api/v1/auth/login", json={
            "email": test_email_a,
            "password": "NewBrandSecurePw999",
        })
        assert res.status_code == 200
        print("  [OK] Login with new password succeeded!")

        # -------------------------------------------------------------
        # Section 6: Logout
        # -------------------------------------------------------------
        print("\n[SECTION 6] Testing Logout...")
        login_data = res.json()
        refresh_to_logout = login_data["refresh_token"]

        res = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_to_logout})
        assert res.status_code == 200
        print("  [OK] Logout successful (200)")

        # Try to refresh with logged-out token
        res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_to_logout})
        assert res.status_code == 401
        print("  [OK] Logged out token is revoked and unusable (401)")

        # Cleanup test accounts
        await users_col.delete_many({"email": {"$in": [test_email_a, test_email_b]}})
        await workspaces_col.delete_many({"_id": {"$in": [ws_id_a, ws_id_b]}})
        await feedback_col.delete_many({"customer_id": "CUST-A-1"})

        print("\n" + "=" * 70)
        print("ALL AUTHENTICATION & WORKSPACE TESTS PASSED WITH 100% SUCCESS!")
        print("=" * 70)

    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(run_auth_test_suite())
