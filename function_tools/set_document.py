from typing import Optional

import chainlit as cl

from augmented import TeamLead


@cl.step(type="tool", name="Set document")
def set_document(document_name: str, document_json: str) -> str:
  teamlead: Optional[TeamLead] = cl.user_session.get("teamlead")
  assert teamlead is not None, "teamlead should be set"
  if document_name in teamlead.documents:
    d_retval = f"Document {document_name} already exists. Overwriting it."
  else:
    d_retval = f"Document {document_name} created."
  teamlead.documents[document_name] = document_json
  return d_retval