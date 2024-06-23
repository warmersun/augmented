import os

import chainlit as cl
from openai import AsyncOpenAI

# refer to https://docs.perplexity.ai/docs/pricing for Pricing

@cl.step(type="tool", name="Search for Up-to-date Answer Using Perplexity")
async def web_search_qa(question: str) -> str:
  messages = [
    {
      "role": "system",
      "content": 
        "You are an artificial intelligence assistant "
        "and you need to answer the user's question with recent, upt-to-date information from the world-wide web.",
      },
      {
        "role": "user",
        "content": f"{question}"
      },
    ]

  current_step = cl.context.current_step
  current_step.input = question
  
  
  client = AsyncOpenAI(api_key=os.environ['PERPLEXITY_API_KEY'], base_url="https://api.perplexity.ai")
  response = await client.chat.completions.create(
    model="llama-3-sonar-large-32k-online",
    messages=messages
  )
  return response.choices[0].message.content