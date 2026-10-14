import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv('backend/.env')
sys.path.insert(0, 'backend')

from motor.motor_asyncio import AsyncIOMotorClient
from services.title_normalizer import normalize_topic_titles

async def migrate():
    client = AsyncIOMotorClient(os.getenv('MONGO_URI'))
    db = client[os.getenv('DB_NAME')]
    cursor = db.workspace_insights.find({})
    count = 0
    async for doc in cursor:
        ws_id = doc.get('workspace_id')
        pps = doc.get('pain_points', [])
        clusters = doc.get('feature_clusters', [])
        themes = doc.get('themes', [])
        
        upgraded_pps = normalize_topic_titles(pps, 'pain_point') if pps else []
        upgraded_clusters = normalize_topic_titles(clusters, 'cluster') if clusters else []
        upgraded_themes = normalize_topic_titles(themes, 'theme') if themes else []
        
        await db.workspace_insights.update_one(
            {'_id': doc['_id']},
            {'$set': {
                'pain_points': upgraded_pps,
                'feature_clusters': upgraded_clusters,
                'themes': upgraded_themes
            }}
        )
        count += 1
        print(f"Migrated workspace {ws_id}: {len(upgraded_pps)} pain points normalized")
    print(f"Done. Total workspaces upgraded: {count}")

if __name__ == '__main__':
    asyncio.run(migrate())
