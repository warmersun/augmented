import json
import os
from typing import Awaitable, Callable, Optional

import yaml
from openai import AsyncOpenAI

from augmented import Worker


class TeamLead:
  @classmethod
  def _load_config(cls, filepath: str) -> dict:
    with open(filepath, 'r') as file:
      return yaml.safe_load(file)
      
  def __init__(self, ask_user_func: Callable[[str], Awaitable[str]]):
    self.documents = {}
    self._worker : Optional[Worker] = None
    self.config = self._load_config('config.yaml')
    self.function_definitions = self._load_config('function_definitions.yaml')
    self.next_worker_ndx = 0
    self.ask_user_func =  ask_user_func
    self.async_client = AsyncOpenAI(
      api_key=os.environ['OPENAI_API_KEY'],
    )
    self.thread = None


  async def get_next_worker(self) -> Optional[Worker]:
    for index, (worker_name, worker_config) in enumerate(self.config.items()):
      if index == self.next_worker_ndx:
        self.next_worker_ndx += 1
        # need to check if the input for the worker is available
        for input_name in worker_config['inputs']:
          input = self.documents.get(input_name)
          if input is None:
            # we don't have the input, so we need to ask the user
            input = await self.ask_user_func(input_name)
            self.documents[input_name] = input
        # assemble list of inputs
        inputs = [(input_name, self.documents[input_name]) for input_name in worker_config['inputs']]  
        # now we can construct the worker
        # assume it does not exist. If it did we overwrite it
        # create the assistant
        assistant = None
        if worker_config['assistant'].get('id') is not None:
          assistant = await self.async_client.beta.assistants.retrieve(worker_config['assistant']['id'])
        else:
          tool_functions = []
          if worker_config['assistant'].get('functions') is not None:
            for function_name in worker_config['assistant']['functions']:
              tool_functions.append(
                {
                  "type": "function", 
                  "function": json.loads(self.function_definitions[function_name])
                }
              )
          assistant = await self.async_client.beta.assistants.create(
            name= worker_config['assistant']['name'],
            instructions=worker_config['assistant']['instruction'],
            model=worker_config['assistant'].get('model','gpt-4o'),
            tools = tool_functions
          )
        # Let's deal with the thread. Normally, workers will start a new thread...
        # unless the new_thread is set to false in the config.
        # This allows observers - and other assistants - to continue the thread.
        if worker_config.get('new_thread', True) or self.thread is None:
          self.thread = await self.async_client.beta.threads.create()
        # pass it in to the worker
        self._worker = Worker(
          name = worker_name,
          task_desc=worker_config.get('task'),
          assistant=assistant,
          inputs=inputs,
          thread= self.thread,
          has_user_interaction=worker_config.get('has_user_interaction', True),
        )
        return self._worker
    return None

  def save_output(self) -> None:
    assert self._worker is not None, "No worker is running"    
    worker_config = self.config.get(self._worker.name)
    assert worker_config is not None, f"Worker config for {self._worker.name} should exist"
    output_name = worker_config.get('output')
    assert self._worker is not None, "self._worker should be set before calling save_output"
    self.documents[output_name] = self._worker.output
    