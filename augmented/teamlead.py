import json
import os
from typing import Awaitable, Callable, Optional

import yaml
from openai import OpenAI

from augmented import Observer, Worker


class TeamLead:
  @classmethod
  def _load_config(cls, filepath: str) -> dict:
    with open(filepath, 'r') as file:
      return yaml.safe_load(file)
      
  def __init__(self, ask_user_func: Callable[[str], Awaitable[str]]):
    self.documents = {}
    self._worker = None
    self.config = self._load_config('config.yaml')
    self.function_definitions = self._load_config('function_definitions.yaml')
    self.next_worker_ndx = 0
    self.ask_user_func =  ask_user_func
    self.client = OpenAI(
      api_key=os.environ['OPENAI_API_KEY'],
    ) 


  async def get_next_worker(self) -> Worker:
    for index, (worker_name, worker_config) in enumerate(self.config.items()):
      if index == self.next_worker_ndx:
        self.next_worker_ndx += 1
        # need to check if the input for the worker is available
        input_name = worker_config['input']
        input = self.documents.get(input_name)
        if input is None:
          # we don't have the input, so we need to ask the user
          input = await self.ask_user_func(input_name)
        # now we can construct the worker
        # assume it does not exist. If it did we overwrite it
        # create the assistant
        assistant = None
        if worker_config['assistant'].get('id') is not None:
          assistant = self.client.beta.assistants.retrieve(worker_config['assistant']['id'])
        else:
          tool_functions = []
          if worker_config['assistant'].get('functions') is not None:
            for function in worker_config['assistant']['functions']:
              tool_functions.append(
                {
                  "type": "function", 
                  "function": json.loads(self.function_definitions[function['name']])
                }
              )
          assistant = self.client.beta.assistants.create(
            name= worker_config['assistant']['name'],
            instructions=worker_config['assistant']['instruction'],
            model="gpt-4o",
            tools = tool_functions
          )              
          # pass it in to the worker
        self._worker = Worker(
          worker_config['task'],
          assistant,
          input
        )
        self.current_worker_name = worker_name
        return self._worker
    return None

  def save_output(self) -> None:
    worker_config = self.config.get(self.current_worker_name)
    output_name = worker_config.get('output')
    output = self._worker.output
    self.documents[output_name] = output

  def get_observer(self) -> Optional[Observer]:
    worker_config = self.config.get(self.current_worker_name)
    observer_config = worker_config.get('observer')
    if observer_config is None:
      return None
    return Observer(
      observer_config.get('name'),
      observer_config.get('instruction'),
      self._worker
    )
    