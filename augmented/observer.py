import json
import os

from openai import AsyncAssistantEventHandler, AsyncOpenAI, OpenAI
from openai.types.beta import Assistant, Thread

from augmented import Worker

# The Observer looks at a previous output and provides an observation such as a summary, an evaluation, a criticism
# It should be passed an assistant that has its instructions include
# 1. JSON mode
# 2. to observe
# e.g. You are an observer. You look at conversations between an AI math tutor and a learner 
# and evaluate it withconstructive criticism. 
# Your job is not to help the user or answer their questions but to observe and analyze the entire conversation. 
# Provide your analysis! Output as JSON structure containing an `analysis` strings"
#
# It will receive the input, the produced output and the entire conversation thread

class Observer:
  def __init__(self, name: str, instructions:str, worker: Worker) -> None:
    self.client = OpenAI(
      api_key=os.environ['OPENAI_API_KEY'],
    ) 
    self.async_client = AsyncOpenAI(
      api_key=os.environ['OPENAI_API_KEY'],
    )
    self.assistant = self.client.beta.assistants.create(
      name=name,
      instructions=instructions,
      model="gpt-4o",
    )
    self.input = worker.input
    self.output = worker.output
    self.thread = worker.thread
    self.observation = ""

  def observe(self) -> str:
    run = self.client.beta.threads.runs.create_and_poll(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id,
      additional_instructions=
        f"The original input was:\n***\n{self.input}.\n***\nThe original output was:\n***\n{self.output}\n***\n"
    )
    if run.status == 'completed':
      messages = self.client.beta.threads.messages.list(
          thread_id=self.thread.id,
          run_id=run.id
      )
      # Check if there are messages in the response
      if messages.data:
          for message in messages:
              # Access the text content of each message
              if message.content[0].type == 'text':
                  observation_text = message.content[0].text.value
                  try:
                      observation_json = json.loads(observation_text)
                      self.observation = observation_json.get("observation", "Failed to generate observation.")
                  except json.JSONDecodeError:
                      self.observation = "Failed to decode JSON"
                  except Exception as e:
                      self.observation = f"Unexpected error: {str(e)}"
                  return str(self.observation)
              else:
                  # Handle case where message content is not text
                  return "Message content is not text."
      else:
          # Handle case where no messages are found
          return "No messages found."

    # Handle case where output run status is not completed
    return f"Output run status: {run.status}"


