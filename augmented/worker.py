
from openai import OpenAI
from openai.types.beta import Assistant
from openai.types.beta.threads import Message


class Worker:
  def __init__(self, assistant: Assistant) -> None:
    self.assistant = assistant

    self.client = OpenAI(
      api_key="sk-proj-lIS7EjUSNLIxMzZXKukNT3BlbkFJpxzt48gerFrWOUxAHQGp",
    ) 
    self.thread = self.client.beta.threads.create()
    self.run = None

  def __submit_user_message(self, msg: str) -> Message:
    message = self.client.beta.threads.messages.create(
      thread_id=self.thread.id,
      role = "user",
      content = msg
    )
    return message
  
  def next_step(self, prompt: str) -> str:
    message = self.__submit_user_message(prompt)

    self.run = self.client.beta.threads.runs.create_and_poll(
      thread_id=self.thread.id,
      assistant_id=self.assistant.id
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
              return message_text
      else:
          return "No messages found."


    
    return self.run.status
    