import json
import os

from openai import AsyncAssistantEventHandler, AsyncOpenAI, OpenAI
from openai.types.beta import Assistant


class Worker:
  def __init__(self, name: str, instructions: str, input: str) -> None:
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
    self.input = input
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

  def finish(self) -> None:
    self.finished = True
  
  def is_finished(self) -> bool:
    return self.finished

  import json

  def generate_output(self) -> str:
      output_run = self.client.beta.threads.runs.create_and_poll(
          thread_id=self.thread.id,
          assistant_id=self.assistant.id,
          # TODO: support multiple outputs
          instructions= (self.assistant.instructions or "") + "Generate the output. Remember, the output is a JSON object with the just a single key: 'output' and the value is a string.",
          additional_instructions=f"The input is: {self.input}",
          response_format={"type": "json_object"}
      )
      if output_run.status == 'completed':
          messages = self.client.beta.threads.messages.list(
              thread_id=self.thread.id,
              run_id=output_run.id
          )
          # Check if there are messages in the response
          if messages.data:
              for message in messages:
                  # Access the text content of each message
                  if message.content[0].type == 'text':
                      output_text = message.content[0].text.value
                      try:
                          output_json = json.loads(output_text)
                          self.output = output_json.get("output", "Failed to generate output")
                      except json.JSONDecodeError:
                          self.output = "Failed to decode JSON"
                      except Exception as e:
                          self.output = f"Unexpected error: {str(e)}"
                      return str(self.output)
                  else:
                      # Handle case where message content is not text
                      return "Message content is not text."
          else:
              # Handle case where no messages are found
              return "No messages found."

      # Handle case where output run status is not completed
      return f"Output run status: {output_run.status}"
  
  async def get_next_assistant_message(self, event_handler: AsyncAssistantEventHandler) -> None:
    async with self.async_client.beta.threads.runs.stream(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id,
      additional_instructions=f"The input is: {self.input}",
      event_handler=event_handler
    ) as stream:
      await stream.until_done()

  def output_is_good_to_go(self) -> None:
    self.output_confirmed = True

  def output_needs_work(self, feedback: str) -> None:
    self.output_confirmed = False
    self.finished = False
    # need to send the AI a message that the output needs work
    self.submit_user_message(
      f"The output needs work." \
      f"This is the output that was generated but not good to go:\n***\n{self.output}\n***\nThis is my feedback: {feedback}"
    )
  

    