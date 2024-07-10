from typing import Optional

import chainlit as cl

from augmented import TeamLead


@cl.step(type="tool", name="Set document")
def set_document(document_name: str, document_json: str) -> str:
  teamlead: Optional[TeamLead] = cl.user_session.get("teamlead")
  assert teamlead is not None, "teamlead should be set"
  # iterate on teamlead.config['workers'] and find which work has this document_name as one of its inputs
  workers_using_this_document_as_input = []
  for worker_name, worker_config in teamlead.config['workers'].items():
    if document_name in worker_config['inputs']:
      workers_using_this_document_as_input.append(worker_name)      
  worker_list = ', '.join(workers_using_this_document_as_input) if workers_using_this_document_as_input else 'None'
  if document_name in teamlead.documents:
    d_retval = f"Document {document_name} already exists. Overwriting it. Workers using this document as input: {worker_list}"
  else:
    d_retval = f"Document {document_name} created. Workers using this document as input: {worker_list}"
  teamlead.documents[document_name] = document_json
  return d_retval