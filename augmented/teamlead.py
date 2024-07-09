import json
import os
from typing import Awaitable, Callable, Optional, Type

import yaml
from jsonschema import SchemaError, ValidationError, validate
from openai import AsyncAssistantEventHandler, AsyncOpenAI
from openai.types.beta.assistant import Assistant

from .planner import Planner
from .worker import Worker


class TeamLead:
  @classmethod
  def _load_config(cls, filepath: str) -> dict:
    with open(filepath, 'r') as file:
      return yaml.safe_load(file)

  @classmethod
  def load_schema(cls, filepath: str) -> dict:
    with open(filepath, 'r') as file:
      return json.load(file)

  @classmethod
  def validate_config(cls, config: dict, schema: dict) -> None:
    try:
      validate(instance=config, schema=schema)
    except ValidationError as e:
        raise AssertionError(f"YAML file is invalid. Error: {e.message}\nSchema Path: {e.schema_path}\nInstance Path: {e.path}") from e
    except SchemaError as e:
        raise AssertionError(f"Schema is invalid. Error: {e.message}") from e
      
  def __init__(self, ask_user_func: Callable[[str], Awaitable[str]]):
    self.documents = {}
    self._workers = {}
    self.config = self._load_config('config.yaml')
    schema = self.load_schema('schema.json')
    self.validate_config(self.config, schema)
    self.function_definitions = self._load_config('function_definitions.yaml')
    self.next_worker_ndx = 0
    self.ask_user_func =  ask_user_func
    self.async_client = AsyncOpenAI(
      api_key=os.environ['OPENAI_API_KEY'],
    )
    self.thread = None
    self._planner = None
    self.planner_thread = None
    self._current_worker_name = None
    self._ids_of_assistants_created = []

  async def _get_assistant(self, assistant_config: dict) -> Assistant:
    # now we can construct the worker
    # assume it does not exist. If it did we overwrite it
    # create the assistant
    assistant = None
    if assistant_config.get('id') is not None:
      # retrieve assistant by ID
      assistant = await self.async_client.beta.assistants.retrieve(assistant_config['id'])
    else:
      # create assistant from the config
      tool_functions = []
      if assistant_config.get('functions') is not None:
        for function_name in assistant_config['functions']:
          tool_functions.append(
            {
              "type": "function", 
              "function": json.loads(self.function_definitions[function_name])
            }
          )
      assistant = await self.async_client.beta.assistants.create(
        name= assistant_config['name'],
        instructions=assistant_config['instruction'],
        model=assistant_config.get('model','gpt-4o'),
        tools = tool_functions
      )
      self._ids_of_assistants_created.append(assistant.id)
    return assistant

  async def get_worker(self, worker_name: str, message_event_handler_class: Type[AsyncAssistantEventHandler], output_event_handler_class: Type[AsyncAssistantEventHandler]) -> Optional[Worker]:
    self._current_worker_name = worker_name
    if worker_name not in self.config['workers']:
      return None
    # reuse existing workers if we have already created them
    if self._workers.get(worker_name) is None:
      worker_config = self.config['workers'][worker_name]
      # need to check if the input for the worker is available
      for input_name in worker_config['inputs']:
        input = self.documents.get(input_name)
        if input is None:
          # we don't have the input, so we need to ask the user
          input = await self.ask_user_func(input_name)
          self.documents[input_name] = input
      # assemble list of inputs
      inputs = [(input_name, self.documents[input_name]) for input_name in worker_config['inputs']]
      assistant = await self._get_assistant(worker_config['assistant'])
      # Let's deal with the thread. Normally, workers will start a new thread...
      # unless the new_thread is set to false in the config.
      # This allows observers - and other assistants - to continue the thread.
      if worker_config.get('new_thread', True) or self.thread is None:
        self.thread = await self.async_client.beta.threads.create()
      # pass it in to the worker
      self._workers[worker_name] = Worker(
        name = worker_name,
        task_desc=worker_config.get('task'),
        assistant=assistant,
        inputs=inputs,
        output_name=worker_config['output'],
        thread=self.thread,
        message_event_handler_class=message_event_handler_class,
        output_event_handler_class=output_event_handler_class,
        has_user_interaction=worker_config.get('has_user_interaction', True),
      )
    return self._workers[worker_name]

  def save_output(self) -> None:
    assert self._current_worker_name is not None, "No worker is currently running"
    workers_config = self.config.get("workers", {})
    worker_config = workers_config.get(self._current_worker_name)
    assert worker_config is not None, f"Worker config for {self._current_worker_name} should exist"
    output_name = worker_config.get('output')
    self.documents[output_name] = self._workers[self._current_worker_name].output

  async def get_planner(self, message_event_handler_class: Type[AsyncAssistantEventHandler]) -> Planner:
    assert self.config['planner'] is not None, "No planner config"
    planner_config = self.config['planner']
    assistant = await self._get_assistant(planner_config['assistant'])
    if self._planner is None:
      if self.planner_thread is None:
        self.planner_thread = await self.async_client.beta.threads.create()
      self._planner = Planner(assistant, self.planner_thread, self.config, message_event_handler_class)
    return self._planner
    
  async def delete_any_assistant_created(self) -> None:
    # delete any assistants that were created by this teamlead
    for assistant_id in self._ids_of_assistants_created:
      await self.async_client.beta.assistants.delete(assistant_id)