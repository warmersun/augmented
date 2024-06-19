import json

from openai import OpenAI, AssistantEventHandler
from openai.types.beta import Assistant
from openai.types.beta.threads import Message


class Worker:
  def __init__(self, assistant: Assistant, event_handler: AssistantEventHandler, input: str) -> None:
    self.assistant = assistant
    self.event_handler = event_handler
    self.additional_instructions = f"The input is: {input}"

    self.client = OpenAI(
      api_key="sk-proj-lIS7EjUSNLIxMzZXKukNT3BlbkFJpxzt48gerFrWOUxAHQGp",
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
        "Produce the output in JSON format, as a JSON structure with a single string"
        "called `output`.\n" + self.additional_instructions,
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
  
  def get_next_assistant_message(self) -> str:
    self.run = self.client.beta.threads.runs.create_and_poll(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id,
      additional_instructions=self.additional_instructions
    )
    if self.run.status == 'completed':
      messages = self.client.beta.threads.messages.list(
        thread_id=self.thread.id,
        run_id = self.run.id
      )
      # Check if there are messages in the response
      if messages.data:
        for message in messages:
          # Access the text content of each message
          if message.content[0].type == 'text':
            message_text = message.content[0].text.value
          else:
            message_text = "n/a"
          self.check_if_we_finished(message_text)
          return message_text
      else:
        # TODO: fix
        return "No messages found."
    # TODO: fix    
    return self.run.status
  
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
  

    