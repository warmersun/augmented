import os

from openai import AsyncAssistantEventHandler, AsyncOpenAI, NotGiven, OpenAI
from openai.types.beta import Assistant, Thread

from augmented.util import json_mode_instruction_ending


class Worker:
  def __init__(self, name: str, task_desc: str, assistant: Assistant, inputs: list[tuple[str, str]], thread: Thread, has_user_interaction=True ) -> None:
    self.async_client = AsyncOpenAI(
      api_key=os.environ['OPENAI_API_KEY'],
    )
    self.name = name
    self.assistant = assistant
    self.task = task_desc
    self.inputs = inputs
    self.thread = thread
    self.run_id = None
    self.outputs = None
    self.has_user_interaction = has_user_interaction

  async def submit_user_message(self, msg: str) -> None:
    if self.thread is None:
      self.thread = await self.async_client.beta.threads.create()
      
    await self.async_client.beta.threads.messages.create(
      thread_id=self.thread.id,
      role = "user",
      content = msg
    )

  async def generate_output(self, event_handler: AsyncAssistantEventHandler) -> str:
    if self.thread is None:
       return "No thread."
    async with self.async_client.beta.threads.runs.stream(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id,
      tools = [],
      instructions= (self.assistant.instructions or "") + json_mode_instruction_ending(),
      additional_instructions="The inputs are:\n" + "\n\n".join([f"{name}:\n{value}" for name, value in self.inputs]),
      response_format={"type": "json_object"},
      event_handler=event_handler
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
    else:
      # Handle case where no messages are found
      return "No messages found."
        
  async def get_next_assistant_message(self, event_handler: AsyncAssistantEventHandler) -> None:
    async with self.async_client.beta.threads.runs.stream(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id,
      additional_instructions="The inputs are:\n" + "\n\n".join([f"{name}:\n{value}" for name, value in self.inputs]),
      event_handler=event_handler
    ) as stream:
      try:
        # TODO: why do we need this?
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

  async def output_needs_work(self, feedback: str) -> None:
    # need to send the AI a message that the output needs work
    await self.submit_user_message(
      f"The output needs work." \
      f"This is the output that was generated but not good to go:\n***\n{self.output}\n***\n" \
      f"and this is my feedback: {feedback}.\n" \
      f"Please confirm that you understood and list briefly what you would change to make the output better."
    )
  

    