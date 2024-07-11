import json
from typing import Optional

import chainlit as cl

from augmented import TeamLead


@cl.step(type="tool", name="Get document")
def get_document(document_name: str) -> str:
  teamlead: Optional[TeamLead] = cl.user_session.get("teamlead")
  assert teamlead is not None, "teamlead should be set"
  d_retval = teamlead.documents.get(document_name, "Document has not been generated yet.")
  if isinstance(d_retval, str):
    return d_retval
  else:
    return json.dumps(d_retval, indent=4)