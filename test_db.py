import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postgrespassword@localhost:5433/postgres")
    rows = await conn.fetch("SELECT left(content, 100), ts_rank(fts, websearch_to_tsquery('spanish', '¿Quién es Bryan Bobadilla?')) as rank FROM documents ORDER BY rank DESC LIMIT 10")
    for r in rows:
        print(f"{r['rank']} | {r['left']}")
    await conn.close()

asyncio.run(main())
