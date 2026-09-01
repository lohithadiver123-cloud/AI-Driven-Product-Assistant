"""Script to import sample feedback and support tickets into all workspaces."""
import asyncio
import os
import sys
import pandas as pd

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import connect_to_mongo, close_mongo_connection, get_collection
from app.database.collections import Collections
from app.services.ingestion import ingestion_service


async def main():
    await connect_to_mongo()
    
    workspaces_col = get_collection(Collections.WORKSPACES)
    users_col = get_collection(Collections.USERS)
    
    workspaces = await workspaces_col.find({}).to_list(length=100)
    print(f"Found {len(workspaces)} workspace(s):")
    for ws in workspaces:
        print(f" - Workspace ID: {ws['_id']}, Name: {ws.get('name')}, Owner: {ws.get('owner_id')}")

    if not workspaces:
        print("No workspaces found. Checking users...")
        users = await users_col.find({}).to_list(length=100)
        print(f"Found {len(users)} user(s).")
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    feedback_csv_path = os.path.join(base_dir, "data", "raw", "sample_feedback.csv")
    tickets_csv_path = os.path.join(base_dir, "data", "raw", "sample_support_tickets.csv")

    if not os.path.exists(feedback_csv_path):
        print(f"Error: {feedback_csv_path} does not exist!")
        return

    df_feedback = pd.read_csv(feedback_csv_path)
    df_tickets = pd.read_csv(tickets_csv_path) if os.path.exists(tickets_csv_path) else None

    for ws in workspaces:
        ws_id = str(ws["_id"])
        ws_name = ws.get("name", "Unknown Workspace")
        print(f"\n--- Importing into Workspace: '{ws_name}' ({ws_id}) ---")

        # Ingest feedback
        report_fb = await ingestion_service.ingest_feedback_dataframe(
            df=df_feedback.copy(),
            filename="sample_feedback.csv",
            workspace_id=ws_id,
        )
        print(f"Feedback Ingested: {report_fb.processed_records} processed, {report_fb.duplicate_records} duplicates skipped.")

        # Ingest tickets if present
        if df_tickets is not None:
            report_tk = await ingestion_service.ingest_support_tickets_dataframe(
                df=df_tickets.copy(),
                filename="sample_support_tickets.csv",
                workspace_id=ws_id,
            )
            print(f"Support Tickets Ingested: {report_tk.processed_records} processed, {report_tk.duplicate_records} duplicates skipped.")

    print("\nDataset ingestion completed successfully!")
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
