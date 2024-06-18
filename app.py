import chainlit as cl
from openai import OpenAI
from openai.types.beta import Assistant

from augmented import Worker


@cl.on_chat_start
async def start():
    client = OpenAI(
      api_key="sk-proj-lIS7EjUSNLIxMzZXKukNT3BlbkFJpxzt48gerFrWOUxAHQGp",
    ) 
    assistant =  client.beta.assistants.create(
      name="Content Worker",
      instructions="you are a content creator assistant. You work together with the user to create lesson content for the learning goals specified in the input. Input: learning goals. Output: content for a lesson plan.",
      model="gpt-4o",
    )
    cl.user_session.set("worker", Worker(assistant))

@cl.on_message
async def main(message: cl.Message):
    worker = cl.user_session.get("worker")
    if worker:
        # Send a response back to the user
        await cl.Message(
            content=worker.next_step(message.content)
        ).send()

if __name__ == "__main__":
  from chainlit.cli import run_chainlit
  run_chainlit(__file__)