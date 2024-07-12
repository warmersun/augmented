import asyncio
import os
from typing import Optional

import chainlit as cl
import httpx

# Refer to https://api.search.brave.com/app/subscriptions/subscribe?tab=ai

@cl.step(type="tool", name="Search the Web Using Brave Search")
async def web_search_brave(query: str, freshness : Optional[str] = None) -> list:
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": os.environ['BRAVE_SEARCH_API_KEY']
    }
    params = {
        "q": query,
        "safesearch": "strict",
        "text_decorations": 0,
        "result_filter": "news,web",
        "extra_snippets": 1
    }
    if freshness is not None:
        params["freshness"] = freshness

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        raw_brave_response = response.json()

    def filter_results(results):
        filtered_results = []
        for result in results:
            filtered_results.append({
                "title": result.get("title"),
                "url": result.get("url"),
                "age": result.get("age"),
                "extra_snippets": result.get("extra_snippets")
            })
        return filtered_results


    processed_brave_response = []
    if "web" in raw_brave_response and "results" in raw_brave_response["web"]:
        processed_brave_response.extend(filter_results(raw_brave_response["web"]["results"]))
    if "news" in raw_brave_response and "results" in raw_brave_response["news"]:
        processed_brave_response.extend(filter_results(raw_brave_response["news"]["results"]))
        
    return processed_brave_response
