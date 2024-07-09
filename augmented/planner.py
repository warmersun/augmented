from typing import Type

from openai import AsyncAssistantEventHandler
from openai.types.beta import Assistant, Thread

from .teammember import TeamMember


class Planner(TeamMember):
  # note: Planner gets the entire, original config
  def __init__(self, assistant: Assistant, thread: Thread, config: dict, message_event_handler_class: Type[AsyncAssistantEventHandler]) -> None:
    super().__init__("planner", assistant, thread, message_event_handler_class)
    self._set_additional_instructions(config)

  # the inputs and outputs create a graph where documents are the nodes
  # and workers are edges
  #
  # format: Edge List with Named Edges:
  # e.g.
  # Edge1: A -> B
  # Edge2: A -> C
  # Edge3: B -> D
  # Edge4: C -> D  
  def _set_additional_instructions(self, config: dict) -> None:
    edge_list = []
    for worker, documents in config['workers'].items():
        inputs = ', '.join(documents['inputs'])
        output = documents['output']
        edge_list.append(f"{worker}: {inputs} -> {output}")
    d_instructions = "The list of workers are:\n" + '\n'.join(edge_list)
    self.additional_instructions = d_instructions