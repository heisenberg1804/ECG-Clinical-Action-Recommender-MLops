#!/usr/bin/env python3
"""Initialize database schema for prediction logging."""
import asyncio

import asyncpg

from src.db import ensure_schema, postgres_dsn

DATABASE_URL = postgres_dsn()

async def init_db():
    """Create tables."""
    print("🔄 Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)

    print("📝 Creating tables...")
    await ensure_schema(conn)

    print("✅ Database initialized successfully!")

    # Verify
    count = await conn.fetchval("SELECT COUNT(*) FROM predictions")
    print(f"📊 Current predictions in DB: {count}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(init_db())
