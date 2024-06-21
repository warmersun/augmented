import yaml
from augmented import Worker, Observer
from typing import Callable, Awaitable, Optional, List, Dict, Union

class TeamLead:
  @classmethod
  def _load_config(cls, filepath: str) -> dict:
    with open(filepath, 'r') as file:
      return yaml.safe_load(file)
      
  def __init__(self, ask_user_func: Callable[[str], Awaitable[str]]):
    self.documents = {}
    self._worker = None
    self.config = self._load_config('config.yaml')
    self.next_worker_ndx = 0
    self.ask_user_func =  ask_user_func

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
        self._worker = Worker(
          worker_config['assistant']['name'],
          worker_config['assistant']['instruction'],
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
    