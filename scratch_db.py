import asyncio
import asyncpg
async def main():
    conn = await asyncpg.connect("postgresql://postgres:postgrespassword@localhost:5433/postgres")
    await conn.execute("DELETE FROM documents;")
    await conn.close()
asyncio.run(main())
