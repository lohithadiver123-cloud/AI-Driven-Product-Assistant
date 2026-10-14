"""
End-to-end check of outcome tracking against the running API.

Imports two CSVs into one fresh workspace and reads the comparison back, so the
feature is exercised through the interface the app actually uses rather than
through the service directly.

The workspace it creates is removed again at the end, so repeated runs leave no
residue in the account. Pass --keep to leave it behind for browsing in the UI.

Usage: ./.venv/Scripts/python.exe tools/_outcome_e2e.py [--keep]
"""

import csv
import io
import json
import sys

import requests

sys.path.insert(0, __file__.rsplit("tools", 1)[0])

BASE = "http://127.0.0.1:8000"
EMAIL = "lohith123@gmail.com"
PASSWORD = "lohith"
WORKSPACE_NAME = "Outcome E2E"

CRASH = [
    "the app crashes every time i open the playlist screen",
    "crashes whenever i open the playlist screen on my phone",
    "app crashes on the playlist screen after the update",
]
DL = [
    "please add offline downloads so i can listen without data",
    "i want offline downloads for my saved albums",
    "add offline download support for music please",
]
FILL = [
    "great app i love the music library and the sound quality",
    "the sound quality is excellent and the library is huge",
]


def csv_bytes(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["title", "content", "rating", "source"])
    for index, (text, rating) in enumerate(rows):
        writer.writerow([f"review {index}", text, rating, "app_review"])
    return buffer.getvalue().encode("utf-8")


def main():
    session = requests.Session()
    login = session.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if login.status_code != 200:
        print("login failed", login.status_code, login.text[:200])
        return 1
    session.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    workspace = session.post(
        f"{BASE}/api/workspaces",
        json={"name": WORKSPACE_NAME, "description": "Temporary workspace for the outcome check"},
    )
    if workspace.status_code not in (200, 201):
        print("workspace create failed", workspace.status_code, workspace.text[:300])
        return 1
    workspace_id = workspace.json()["id"] if "id" in workspace.json() else workspace.json()["_id"]
    print(f"workspace {workspace_id}")

    earlier = [(CRASH[index % len(CRASH)], 1) for index in range(40)] + [
        (FILL[index % len(FILL)], 5) for index in range(60)
    ]
    later = [(CRASH[index % len(CRASH)], 2) for index in range(10)] + [
        (FILL[index % len(FILL)], 5) for index in range(90)
    ]

    for name, rows in (("earlier.csv", earlier), ("later.csv", later)):
        response = session.post(
            f"{BASE}/api/feedback/import",
            data={"workspace_id": workspace_id, "source": "app_review"},
            files={"file": (name, csv_bytes(rows), "text/csv")},
        )
        print(f"import {name}: {response.status_code} {str(response.json())[:120]}")

    batches = session.get(f"{BASE}/api/outcome/{workspace_id}/batches")
    print("batches:", json.dumps(batches.json(), indent=2)[:400])

    comparison = session.get(f"{BASE}/api/outcome/{workspace_id}/compare")
    if comparison.status_code != 200:
        print("compare failed", comparison.status_code, comparison.text[:400])
        return 1
    payload = comparison.json()
    print("status:", payload["status"])
    print("headline:", payload.get("headline"))
    print("confidence:", payload.get("confidence"), "gap_days:", payload.get("gap_days"))
    print("before:", {k: payload["before"][k] for k in ("total", "problem_per_100", "avg_rating", "health_score")})
    print("after :", {k: payload["after"][k] for k in ("total", "problem_per_100", "avg_rating", "health_score")})

    for row in payload.get("themes", []):
        print(f"  {row['direction']:<22} {row['before_count']:>4} -> {row['after_count']:>4}  {row['title']}")

    export = session.get(f"{BASE}/api/outcome/{workspace_id}/export")
    print("export:", export.status_code, export.headers.get("content-type"), len(export.text), "chars")
    print("--- export head ---")
    print("\n".join(export.text.splitlines()[:14]))

    return 0


def cleanup():
    """Remove every throwaway workspace this tool has created, and its records."""
    import asyncio

    import database

    async def run():
        await database.connect_to_mongo()
        if not database._mongodb_available:
            print("cleanup skipped: no MongoDB connection")
            return
        workspaces = await database.db.workspaces.find({"name": WORKSPACE_NAME}).to_list(length=None)
        for workspace in workspaces:
            workspace_id = str(workspace["_id"])
            removed = 0
            for collection in ("feedback", "import_logs", "workspace_insights"):
                result = await database.db[collection].delete_many({"workspace_id": workspace_id})
                removed += result.deleted_count
            await database.db.workspaces.delete_one({"_id": workspace["_id"]})
            print(f"removed workspace {workspace_id} and {removed} related documents")
        if not workspaces:
            print("cleanup: nothing to remove")

    asyncio.run(run())


if __name__ == "__main__":
    status = main()
    if "--keep" not in sys.argv[1:]:
        cleanup()
    sys.exit(status)
