import json
import os

from openai import AsyncAssistantEventHandler, AsyncOpenAI, OpenAI
from openai.types.beta import Assistant


class Worker:
  def __init__(self, assistant: Assistant, input: str) -> None:
    self.assistant = assistant
    self.additional_instructions = f"The input is: {input}"

    self.client = OpenAI(
      api_key=os.environ['OPENAI_API_KEY'],
    ) 
    self.async_client = AsyncOpenAI(
      api_key=os.environ['OPENAI_API_KEY'],
    )
    self.thread = self.client.beta.threads.create()
    self.run = None
    self.finished = False
    self.output = None
    self.output_confirmed = False

  def submit_user_message(self, msg: str) -> None:
    message = self.client.beta.threads.messages.create(
      thread_id=self.thread.id,
      role = "user",
      content = msg
    )
    self.check_if_we_finished(msg)

  def check_if_we_finished(self, msg: str) -> None:
    self.finished = msg.upper().endswith("FINISHED")
  
  def is_finished(self) -> bool:
    return self.finished

  def generate_output(self) -> str:
    output_run =  self.client.beta.threads.runs.create_and_poll(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id,
      # TODO: support multiple outputs
      additional_instructions=
        "Produce the output in JSON format, as a JSON structure with a single string called `output`. Like this:\n{\n    \"output\": \"..example output...\"\n}\n\n" + self.additional_instructions,
      response_format={"type": "json_object"}
    )
    if output_run.status == 'completed':
      messages = self.client.beta.threads.messages.list(
        thread_id=self.thread.id,
        run_id = output_run.id
      )
      # Check if there are messages in the response
      if messages.data:
        for message in messages:
          # Access the text content of each message
          if message.content[0].type == 'text':
            output_text = message.content[0].text.value
            self.output = json.loads(output_text).get("output")
            return self.output
          else:
            # TODO: fix
            return "n/a"
      else:
        # TODO: fix
        return "No messages found."
      
    # TODO: fix    
    return output_run.status
  
  async def get_next_assistant_message(self, event_handler: AsyncAssistantEventHandler) -> None:
    async with self.async_client.beta.threads.runs.stream(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id,
      additional_instructions=self.additional_instructions,
      event_handler=event_handler
    ) as stream:
      await stream.until_done()

  def output_is_good_to_go(self) -> None:
    self.output_confirmed = True

  def output_needs_work(self) -> None:
    self.output_confirmed = False
    self.finished = False
    # need to send the AI a message that the output needs work
    self.submit_user_message(
      f"The output needs work." \
      f"This is the output that was generated but not good to go:\n***\n{self.output}"
    )
  

    