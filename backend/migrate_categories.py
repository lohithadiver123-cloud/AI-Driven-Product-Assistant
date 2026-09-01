"""Utility to normalize all existing database records to the 10 controlled categories."""
import asyncio
from app.database.connection import connect_to_mongo, close_mongo_connection, get_collection
from app.database.collections import Collections
from app.services.classification import classify_feedback, detect_sentiment, detect_priority
from app.services.preprocessing import clean_text


async def migrate():
    await connect_to_mongo()
    coll = get_collection(Collections.FEEDBACK)
    cursor = coll.find()
    updated = 0
    async for doc in cursor:
        text = doc.get("text", "")
        cleaned = doc.get("cleaned_text") or clean_text(text)
        cat, conf = classify_feedback(text, cleaned)
        sent = doc.get("sentiment") or detect_sentiment(text)
        prio = doc.get("priority") or detect_priority(text, cat, sent)

        await coll.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "cleaned_text": cleaned,
                    "category": cat,
                    "category_confidence": conf,
                    "sentiment": sent,
                    "priority": prio,
                }
            },
        )
        updated += 1

    print(f"Successfully normalized and categorized {updated} feedback records!")
    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(migrate())
