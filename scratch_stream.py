import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
import instructor
from anthropic import AsyncAnthropic
from src.models.structured import StructuredAnswer
from instructor import Partial

anthropic_client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
client = instructor.from_anthropic(anthropic_client)

async def main():
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": "Analiza esto y genera campos validos. El texto es: Bryan Bobadilla, Python."}],
            response_model=Partial[StructuredAnswer],
            stream=True
        )
        async for r in response:
            pass # just consume
        print("Final model:")
        print(r.model_dump_json())
    except Exception as e:
        print(f"ERROR: {repr(e)}")

asyncio.run(main())
