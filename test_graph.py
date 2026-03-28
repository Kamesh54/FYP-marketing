import asyncio
import logging
from langgraph_graph import run_marketing_graph

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def main():
    result = await run_marketing_graph(
        user_message="Write a blog post about digital marketing",
        session_id="test-session-123",
        user_id=1,
    )
    print("KEYS RETURNED:", result.keys())
    if "response_options" in result:
        print("RESPONSE OPTIONS FOUND!")
        for opt in result["response_options"]:
            print(" - Option:", opt.get("label"))
            print("   Cost:", opt.get("cost_display"))
            print("   Content Type:", opt.get("content_type"))
            print("   Option ID:", opt.get("option_id"))
    else:
        print("RESPONSE OPTIONS MISSING!")

if __name__ == "__main__":
    asyncio.run(main())
