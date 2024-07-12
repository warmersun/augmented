import os

import chainlit as cl
from openai import AsyncOpenAI

# refer to https://docs.perplexity.ai/docs/pricing for Pricing

@cl.step(type="tool", name="Ask Question for Up-to-Date Answer Using Perplexity")
async def web_search_qa_perplexity(question: str) -> str:
  current_step = cl.context.current_step
  if current_step:
    current_step.input = question
  
  client = AsyncOpenAI(api_key=os.environ['PERPLEXITY_API_KEY'], base_url="https://api.perplexity.ai")
  response = await client.chat.completions.create(
    model="llama-3-sonar-large-32k-online",
    messages=[
      {
        "role": "system",
        "content": 
          "You are an artificial intelligence assistant "
          "and you need to answer the user's question with recent, up-to-date information from the world-wide web.",
        },
        {
          "role": "user",
          "content": f"{question}"
        },
      ]
  )
  # Assert that the response contains the expected structure
  assert response.choices, "No choices in response"
  message = response.choices[0].message
  assert message, "No message in choices" 
  assert message.content, "No content in message"
  return message.content