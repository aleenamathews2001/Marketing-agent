# main.py
import asyncio
from graph.marketing_graph import build_marketing_graph
from core.state import MarketingState
import os
from dotenv import load_dotenv


LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")
LANGCHAIN_ENDPOINT = os.getenv("LANGCHAIN_ENDPOINT")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT")
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2")

async def run_example():
    app = build_marketing_graph()

    initial_state: MarketingState = {
        # "user_goal": "  create a campaign named winter 2035 and assign 5 contact to it ",
        "user_goal":" create a campaign Campaign test AM 2025v3",
        #    "user_goal":"send an marketing email to all contact in this 701fo00000CAgf5AAD campaign",
    #   "user_goal":"create a contact with name Bharath Krishna and email krishbharath3@gmail.com and assign to campaign 701fo00000CAgf5AAD",
    #    "user_goal":" fetch contact associated with campaign 701fo00000CAgf5AAD",
    
        #  "user_goal":" Find all contacts whose  name starts with 'A' and assign them to campaign 701fo00000CD1VeAAL",
         "messages": [],
        "max_iterations": 5,
    }

    final_state = await app.ainvoke(initial_state)
    print("=== FINAL SUMMARY ===")
    print(final_state.get("final_response"))

if __name__ == "__main__":
    asyncio.run(run_example())
