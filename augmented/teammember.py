import os
from abc import ABC, abstractmethod
from typing import Type

from openai import AsyncAssistantEventHandler, AsyncOpenAI
from openai.types.beta import Assistant, Thread


class TeamMember(ABC):
  @abstractmethod
  def __init__(self, name: str, assistant: Assistant, thread: Thread, message_event_handler_class: Type[AsyncAssistantEventHandler]) -> None:
    self.async_client = AsyncOpenAI(
      api_key=os.environ['OPENAI_API_KEY'],
    )
    self.name = name
    self.assistant = assistant
    self.thread = thread
    self.message_event_handler_class = message_event_handler_class
    self.run_id = None
    self.additional_instructions = None

  async def submit_user_message(self, msg: str) -> None:
    await self.async_client.beta.threads.messages.create(
      thread_id=self.thread.id,
      role = "user",
      content = msg
    )

  async def get_next_assistant_message(self) -> None:
    async with self.async_client.beta.threads.runs.stream(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id,
      additional_instructions=self.additional_instructions,
      event_handler=self.message_event_handler_class()
    ) as stream:
      try:
        # TODO: why do we need this? Becasue that is how we can cancel a run
        async for event in stream:
          if event.event == "thread.run.created":
            self.run_id = event.data.id
            break
      finally:
        await stream.until_done()
        self.run_id = None
        
  async def cancel_run(self) -> None:
    if self.run_id is not None:
      try:
        await self.async_client.beta.threads.runs.cancel(
          thread_id=self.thread.id,
          run_id=self.run_id
        )
        self.output = None
      except Exception as e:
        print(f"Error cancelling run: {str(e)}")