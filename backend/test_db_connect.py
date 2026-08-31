import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def main():
    uri = os.getenv("MONGO_URI")
    if not uri:
        raise SystemExit("MONGO_URI not set in .env — please add your Atlas connection string")
    client = AsyncIOMotorClient(uri)
    print(await client.list_database_names())

if __name__ == "__main__":
    asyncio.run(main())
