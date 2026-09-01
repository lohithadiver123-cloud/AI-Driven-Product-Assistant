"""Data ingestion pipeline for customer feedback & support ticket files (CSV & JSON)."""
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import pandas as pd

from app.database.collections import Collections
from app.database.connection import get_collection
from app.schemas.ingestion import IngestionReport, IngestionRowError
from app.services.preprocessing import clean_text
from app.services.classification import classify_feedback, detect_sentiment, detect_priority

logger = logging.getLogger("ai_product_assistant.ingestion")

# Common column name variations
TEXT_COLUMN_CANDIDATES = [
    "text", "feedback", "review", "comment", "issue", "content",
    "description", "message", "body", "customer_feedback", "ticket_body", "subject"
]
CUSTOMER_ID_CANDIDATES = [
    "customer_id", "user_id", "user", "customer", "client_id",
    "author_id", "account_id", "email"
]
TICKET_ID_CANDIDATES = ["ticket_id", "ticket", "issue_id", "id", "reference_id"]
SOURCE_CANDIDATES = ["source", "channel", "platform", "origin", "app", "source_name"]
TYPE_CANDIDATES = ["type", "feedback_type", "kind", "category_type"]
PRIORITY_CANDIDATES = ["priority", "severity", "urgency"]
STATUS_CANDIDATES = ["status", "state", "ticket_status"]
CREATED_AT_CANDIDATES = ["created_at", "date", "timestamp", "created_date", "time"]


class DatasetIngestionService:
    """Service to validate, clean, deduplicate, classify, and persist feedback & support ticket datasets."""

    def __init__(self):
        self.default_feedback_source = "CSV Import"
        self.default_ticket_source = "Support Portal"

    def _detect_column(self, columns: List[str], candidates: List[str]) -> Optional[str]:
        """Find the matching column name regardless of case or whitespace."""
        col_map = {c.strip().lower(): c for c in columns}
        for cand in candidates:
            if cand in col_map:
                return col_map[cand]
        return None

    def _parse_datetime(self, date_val: Any) -> datetime:
        """Parse varied date formats safely into a UTC datetime object."""
        if pd.isna(date_val) or not date_val:
            return datetime.now(timezone.utc)
        if isinstance(date_val, datetime):
            return date_val if date_val.tzinfo else date_val.replace(tzinfo=timezone.utc)
        try:
            dt = pd.to_datetime(date_val)
            if pd.isna(dt):
                return datetime.now(timezone.utc)
            return dt.to_pydatetime().replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    # -------------------------------------------------------------
    # Customer Feedback Ingestion
    # -------------------------------------------------------------
    async def _get_existing_feedback_signatures(self, customer_ids: List[str], workspace_id: Optional[str] = None) -> Set[str]:
        """Fetch existing signatures from MongoDB feedback collection scoped by workspace."""
        collection = get_collection(Collections.FEEDBACK)
        query: Dict[str, Any] = {}
        if workspace_id:
            query["workspace_id"] = workspace_id
        valid_c_ids = [cid for cid in customer_ids if cid]
        if valid_c_ids:
            query["customer_id"] = {"$in": valid_c_ids}

        signatures = set()
        cursor = collection.find(query, {"customer_id": 1, "text": 1, "source": 1})
        async for doc in cursor:
            c_id = str(doc.get("customer_id") or "").strip().lower()
            src = str(doc.get("source") or "").strip().lower()
            txt = str(doc.get("text") or "").strip()
            signatures.add(f"{c_id}:{src}:{txt}")
        return signatures

    async def ingest_feedback_dataframe(
        self,
        df: pd.DataFrame,
        filename: Optional[str] = "uploaded_file",
        default_source: str = "CSV Import",
        workspace_id: Optional[str] = None,
    ) -> IngestionReport:
        """Process a pandas DataFrame of customer feedback records."""
        total_records = len(df)
        valid_records = 0
        duplicate_records = 0
        empty_text_records = 0
        errors: List[IngestionRowError] = []
        documents_to_insert: List[Dict[str, Any]] = []
        categories_summary: Dict[str, int] = {}
        sentiment_summary: Dict[str, int] = {}

        if total_records == 0:
            return IngestionReport(
                success=True,
                message="File was empty. 0 records processed.",
                filename=filename,
                total_records=0,
                valid_records=0,
                processed_records=0,
                duplicate_records=0,
                empty_text_records=0,
                invalid_records=0,
                errors=[],
                inserted_ids=[],
                categories_summary={},
                sentiment_summary={},
            )

        columns = list(df.columns)
        text_col = self._detect_column(columns, TEXT_COLUMN_CANDIDATES)
        customer_id_col = self._detect_column(columns, CUSTOMER_ID_CANDIDATES)
        source_col = self._detect_column(columns, SOURCE_CANDIDATES)
        type_col = self._detect_column(columns, TYPE_CANDIDATES)
        created_at_col = self._detect_column(columns, CREATED_AT_CANDIDATES)

        if not text_col:
            return IngestionReport(
                success=False,
                message=f"Missing required feedback text column. Available columns: {columns}",
                filename=filename,
                total_records=total_records,
                invalid_records=total_records,
                errors=[
                    IngestionRowError(
                        row_index=1,
                        reason=f"No recognizable feedback text column found. Expected one of {TEXT_COLUMN_CANDIDATES}",
                        raw_data={"columns": columns},
                    )
                ],
            )

        c_ids_in_batch = []
        if customer_id_col:
            c_ids_in_batch = [str(x) for x in df[customer_id_col].dropna().unique().tolist()]
        existing_signatures = await self._get_existing_feedback_signatures(c_ids_in_batch, workspace_id)
        seen_in_batch: Set[str] = set()

        for idx, row in df.iterrows():
            row_num = idx + 2 if isinstance(idx, int) else 2
            raw_text = row[text_col]

            if pd.isna(raw_text) or not str(raw_text).strip():
                empty_text_records += 1
                errors.append(
                    IngestionRowError(
                        row_index=row_num,
                        reason="Feedback text field is empty or whitespace only.",
                        raw_data={str(k): ("" if pd.isna(v) else str(v)) for k, v in row.items()},
                    )
                )
                continue

            text_str = str(raw_text).strip()
            customer_id = (
                str(row[customer_id_col]).strip()
                if customer_id_col and not pd.isna(row[customer_id_col])
                else None
            )
            source = (
                str(row[source_col]).strip()
                if source_col and not pd.isna(row[source_col]) and str(row[source_col]).strip()
                else default_source
            )
            type_val = (
                str(row[type_col]).strip()
                if type_col and not pd.isna(row[type_col]) and str(row[type_col]).strip()
                else "review"
            )
            created_at = (
                self._parse_datetime(row[created_at_col])
                if created_at_col
                else datetime.now(timezone.utc)
            )

            sig_key = f"{(customer_id or '').lower()}:{source.lower()}:{text_str}"
            if sig_key in seen_in_batch or sig_key in existing_signatures:
                duplicate_records += 1
                errors.append(
                    IngestionRowError(
                        row_index=row_num,
                        reason="Duplicate feedback record detected (matching customer, source, and text).",
                        raw_data={"customer_id": customer_id, "source": source, "text": text_str[:80]},
                    )
                )
                continue

            seen_in_batch.add(sig_key)
            valid_records += 1

            cleaned_text = clean_text(text_str)
            category, confidence = classify_feedback(text_str, cleaned_text)
            sentiment = detect_sentiment(text_str)
            priority = detect_priority(text_str, category, sentiment)

            categories_summary[category] = categories_summary.get(category, 0) + 1
            sentiment_summary[sentiment] = sentiment_summary.get(sentiment, 0) + 1

            metadata = {}
            for col in columns:
                if col not in [text_col, customer_id_col, source_col, type_col, created_at_col]:
                    val = row[col]
                    if not pd.isna(val):
                        metadata[col] = val

            doc = {
                "workspace_id": workspace_id,
                "customer_id": customer_id,
                "source": source,
                "type": type_val,
                "text": text_str,
                "cleaned_text": cleaned_text,
                "category": category,
                "category_confidence": confidence,
                "sentiment": sentiment,
                "priority": priority,
                "status": "New",
                "created_at": created_at,
                "updated_at": datetime.now(timezone.utc),
                "metadata": metadata,
            }
            documents_to_insert.append(doc)

        inserted_ids = []
        if documents_to_insert:
            collection = get_collection(Collections.FEEDBACK)
            result = await collection.insert_many(documents_to_insert)
            inserted_ids = [str(_id) for _id in result.inserted_ids]
            logger.info("Successfully inserted %d feedback records from %s (workspace: %s)", len(inserted_ids), filename, workspace_id)

        processed_records = len(inserted_ids)
        invalid_records = empty_text_records + len([e for e in errors if "Duplicate" not in e.reason])

        message = (
            f"Successfully ingested {processed_records} feedback records out of {total_records} total rows. "
            f"({duplicate_records} duplicates, {empty_text_records} empty rows skipped)"
        )

        return IngestionReport(
            success=True,
            message=message,
            filename=filename,
            total_records=total_records,
            valid_records=valid_records,
            processed_records=processed_records,
            duplicate_records=duplicate_records,
            empty_text_records=empty_text_records,
            invalid_records=invalid_records,
            errors=errors,
            inserted_ids=inserted_ids,
            categories_summary=categories_summary,
            sentiment_summary=sentiment_summary,
        )

    async def ingest_csv_bytes(
        self,
        content: bytes,
        filename: str = "feedback.csv",
        workspace_id: Optional[str] = None,
    ) -> IngestionReport:
        """Parse raw CSV byte content across multiple encodings and ingest feedback."""
        df = self._read_csv_bytes(content)
        if df is None:
            return IngestionReport(
                success=False,
                message="Failed to parse CSV file across standard encodings.",
                filename=filename,
                total_records=0,
                invalid_records=1,
                errors=[IngestionRowError(row_index=1, reason="CSV decoding error")],
            )
        return await self.ingest_feedback_dataframe(
            df,
            filename=filename,
            default_source="CSV Import",
            workspace_id=workspace_id,
        )

    async def ingest_json_records(
        self,
        records: List[Dict[str, Any]],
        filename: str = "feedback.json",
        workspace_id: Optional[str] = None,
    ) -> IngestionReport:
        """Parse a list of feedback records and ingest."""
        if not isinstance(records, list):
            return IngestionReport(
                success=False,
                message="Invalid JSON payload format: expected an array of feedback records.",
                filename=filename,
                total_records=0,
                invalid_records=1,
                errors=[IngestionRowError(row_index=1, reason="Payload is not a JSON list.")],
            )
        df = pd.DataFrame(records)
        return await self.ingest_feedback_dataframe(
            df,
            filename=filename,
            default_source="JSON Import",
            workspace_id=workspace_id,
        )

    # -------------------------------------------------------------
    # Support Ticket Ingestion Pipeline
    # -------------------------------------------------------------
    async def ingest_support_tickets_dataframe(
        self,
        df: pd.DataFrame,
        filename: Optional[str] = "support_tickets.csv",
        default_source: str = "Support Portal",
        workspace_id: Optional[str] = None,
    ) -> IngestionReport:
        """Process a pandas DataFrame of support tickets."""
        total_records = len(df)
        valid_records = 0
        duplicate_records = 0
        empty_text_records = 0
        errors: List[IngestionRowError] = []
        documents_to_insert: List[Dict[str, Any]] = []
        categories_summary: Dict[str, int] = {}
        sentiment_summary: Dict[str, int] = {}

        if total_records == 0:
            return IngestionReport(
                success=True,
                message="Support ticket file was empty. 0 records processed.",
                filename=filename,
                total_records=0,
                valid_records=0,
                processed_records=0,
                duplicate_records=0,
                empty_text_records=0,
                invalid_records=0,
                errors=[],
                inserted_ids=[],
                categories_summary={},
                sentiment_summary={},
            )

        columns = list(df.columns)
        text_col = self._detect_column(columns, TEXT_COLUMN_CANDIDATES)
        ticket_id_col = self._detect_column(columns, TICKET_ID_CANDIDATES)
        customer_id_col = self._detect_column(columns, CUSTOMER_ID_CANDIDATES)
        source_col = self._detect_column(columns, SOURCE_CANDIDATES)
        priority_col = self._detect_column(columns, PRIORITY_CANDIDATES)
        status_col = self._detect_column(columns, STATUS_CANDIDATES)
        created_at_col = self._detect_column(columns, CREATED_AT_CANDIDATES)

        if not text_col:
            return IngestionReport(
                success=False,
                message=f"Missing required support ticket issue/text column. Available columns: {columns}",
                filename=filename,
                total_records=total_records,
                invalid_records=total_records,
                errors=[
                    IngestionRowError(
                        row_index=1,
                        reason=f"No recognizable issue description column found. Expected one of {TEXT_COLUMN_CANDIDATES}",
                        raw_data={"columns": columns},
                    )
                ],
            )

        # Check existing ticket IDs from DB scoped by workspace
        collection = get_collection(Collections.SUPPORT_TICKETS)
        query = {"workspace_id": workspace_id} if workspace_id else {}
        existing_tickets: Set[str] = set()
        cursor = collection.find(query, {"ticket_id": 1, "text": 1})
        async for doc in cursor:
            if doc.get("ticket_id"):
                existing_tickets.add(str(doc["ticket_id"]).strip().lower())
            if doc.get("text"):
                existing_tickets.add(str(doc["text"]).strip().lower()[:60])

        seen_in_batch: Set[str] = set()

        for idx, row in df.iterrows():
            row_num = idx + 2 if isinstance(idx, int) else 2
            raw_text = row[text_col]

            if pd.isna(raw_text) or not str(raw_text).strip():
                empty_text_records += 1
                errors.append(
                    IngestionRowError(
                        row_index=row_num,
                        reason="Ticket issue description is empty or whitespace only.",
                        raw_data={str(k): ("" if pd.isna(v) else str(v)) for k, v in row.items()},
                    )
                )
                continue

            text_str = str(raw_text).strip()
            ticket_id = (
                str(row[ticket_id_col]).strip()
                if ticket_id_col and not pd.isna(row[ticket_id_col])
                else f"TIK-{1000 + idx}"
            )
            customer_id = (
                str(row[customer_id_col]).strip()
                if customer_id_col and not pd.isna(row[customer_id_col])
                else None
            )
            source = (
                str(row[source_col]).strip()
                if source_col and not pd.isna(row[source_col]) and str(row[source_col]).strip()
                else default_source
            )
            status_val = (
                str(row[status_col]).strip()
                if status_col and not pd.isna(row[status_col]) and str(row[status_col]).strip()
                else "Open"
            )
            created_at = (
                self._parse_datetime(row[created_at_col])
                if created_at_col
                else datetime.now(timezone.utc)
            )

            # Duplicate check
            sig_key = ticket_id.lower() if ticket_id else text_str[:60].lower()
            if sig_key in seen_in_batch or sig_key in existing_tickets:
                duplicate_records += 1
                errors.append(
                    IngestionRowError(
                        row_index=row_num,
                        reason=f"Duplicate ticket detected (ticket_id: {ticket_id}).",
                        raw_data={"ticket_id": ticket_id, "text": text_str[:60]},
                    )
                )
                continue

            seen_in_batch.add(sig_key)
            valid_records += 1

            # Clean & Classify
            cleaned_text = clean_text(text_str)
            category, confidence = classify_feedback(text_str, cleaned_text)
            sentiment = detect_sentiment(text_str)
            
            # Use CSV priority if given, else infer
            priority = (
                str(row[priority_col]).capitalize()
                if priority_col and not pd.isna(row[priority_col])
                else detect_priority(text_str, category, sentiment)
            )

            categories_summary[category] = categories_summary.get(category, 0) + 1
            sentiment_summary[sentiment] = sentiment_summary.get(sentiment, 0) + 1

            metadata = {}
            for col in columns:
                if col not in [text_col, ticket_id_col, customer_id_col, source_col, priority_col, status_col, created_at_col]:
                    val = row[col]
                    if not pd.isna(val):
                        metadata[col] = val

            doc = {
                "workspace_id": workspace_id,
                "ticket_id": ticket_id,
                "customer_id": customer_id,
                "source": source,
                "text": text_str,
                "cleaned_text": cleaned_text,
                "category": category,
                "category_confidence": confidence,
                "sentiment": sentiment,
                "priority": priority,
                "status": status_val,
                "created_at": created_at,
                "updated_at": datetime.now(timezone.utc),
                "metadata": metadata,
            }
            documents_to_insert.append(doc)

        inserted_ids = []
        if documents_to_insert:
            result = await collection.insert_many(documents_to_insert)
            inserted_ids = [str(_id) for _id in result.inserted_ids]
            logger.info("Successfully inserted %d support tickets from %s (workspace: %s)", len(inserted_ids), filename, workspace_id)

        processed_records = len(inserted_ids)
        invalid_records = empty_text_records + len([e for e in errors if "Duplicate" not in e.reason])

        message = (
            f"Successfully ingested {processed_records} support tickets out of {total_records} total rows. "
            f"({duplicate_records} duplicates, {empty_text_records} empty rows skipped)"
        )

        return IngestionReport(
            success=True,
            message=message,
            filename=filename,
            total_records=total_records,
            valid_records=valid_records,
            processed_records=processed_records,
            duplicate_records=duplicate_records,
            empty_text_records=empty_text_records,
            invalid_records=invalid_records,
            errors=errors,
            inserted_ids=inserted_ids,
            categories_summary=categories_summary,
            sentiment_summary=sentiment_summary,
        )

    async def ingest_support_tickets_csv(
        self,
        content: bytes,
        filename: str = "tickets.csv",
        workspace_id: Optional[str] = None,
    ) -> IngestionReport:
        """Parse raw CSV bytes for support tickets."""
        df = self._read_csv_bytes(content)
        if df is None:
            return IngestionReport(
                success=False,
                message="Failed to parse support ticket CSV across standard encodings.",
                filename=filename,
                total_records=0,
                invalid_records=1,
                errors=[IngestionRowError(row_index=1, reason="CSV decoding error")],
            )
        return await self.ingest_support_tickets_dataframe(
            df,
            filename=filename,
            default_source="CSV Import",
            workspace_id=workspace_id,
        )

    async def ingest_support_tickets_json(
        self,
        records: List[Dict[str, Any]],
        filename: str = "tickets.json",
        workspace_id: Optional[str] = None,
    ) -> IngestionReport:
        """Parse a list of support ticket records."""
        if not isinstance(records, list):
            return IngestionReport(
                success=False,
                message="Invalid JSON payload format: expected an array of ticket records.",
                filename=filename,
                total_records=0,
                invalid_records=1,
                errors=[IngestionRowError(row_index=1, reason="Payload is not a JSON list.")],
            )
        df = pd.DataFrame(records)
        return await self.ingest_support_tickets_dataframe(
            df,
            filename=filename,
            default_source="JSON Import",
            workspace_id=workspace_id,
        )

    def _read_csv_bytes(self, content: bytes) -> Optional[pd.DataFrame]:
        """Helper to read CSV bytes trying multiple common encodings."""
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                return pd.read_csv(io.BytesIO(content), encoding=encoding)
            except Exception:
                pass
        return None


# Singleton ingestion service and alias
FeedbackIngestionService = DatasetIngestionService
ingestion_service = DatasetIngestionService()
