from typing import Optional, Type

from openai import AsyncAssistantEventHandler
from openai.types.beta import Assistant, Thread

from .teammember import TeamMember
from .util import json_mode_instruction_ending


class Worker(TeamMember):
  def __init__(self, name: str, task_desc: Optional[str], assistant: Assistant, inputs: list[tuple[str, str]], output_name: str, thread: Thread, message_event_handler_class: Type[AsyncAssistantEventHandler], output_event_handler_class: Type[AsyncAssistantEventHandler], has_user_interaction=True ) -> None:
    super().__init__(name, assistant, thread, message_event_handler_class)
    self.output_event_handler_class = output_event_handler_class
    self.task = task_desc
    self.inputs = inputs
    self.output_name = output_name
    self.output = None
    self.has_user_interaction = has_user_interaction
    self.additional_instructions = "The inputs are:\n" + "\n\n".join([f"{name}:\n{value}" for name, value in self.inputs])

  async def generate_output(self) -> str:
    if self.thread is None:
       return "No thread."
    async with self.async_client.beta.threads.runs.stream(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id,
      tools = [],
      instructions= (self.assistant.instructions or "") + json_mode_instruction_ending(),
      additional_instructions="The inputs are:\n" + "\n\n".join([f"{name}:\n{value}" for name, value in self.inputs]),
      response_format={"type": "json_object"},
      event_handler=self.output_event_handler_class()
    ) as stream:
      try:
        async for event in stream:
          # when the event is thread.run.created
          if event.event == "thread.run.created":
              self.run_id = event.data.id
              break
      finally:
        await stream.until_done()
    assert self.run_id is not None, "Run was not created properly, run.id was not found!"
    messages = await self.async_client.beta.threads.messages.list(
      thread_id=self.thread.id,
      run_id=self.run_id
    )
    self.run_id = None
    # Check if there are messages in the response
    if messages.data:
      for message in messages.data:
          # Access the text content of each message
          if message.content[0].type == 'text':
              try:  
                self.output = message.content[0].text.value
              except Exception as e:
                self.output = f"Unexpected error: {str(e)}"
              return str(self.output)
          else:
              # Handle case where message content is not text
              return "Message content is not text."
    # Fallback error handling
    return "No messages found."

  async def output_needs_work(self, feedback: str) -> None: 
    # need to send the AI a message that the output needs work
    await self.submit_user_message(
      f"The output needs work." \
      f"This is the output that was generated but not good to go:\n***\n{self.output}\n***\n" \
      f"and this is my feedback: {feedback}.\n" \
      f"Please confirm that you understood and list briefly what you would change to make the output better."
    )


    