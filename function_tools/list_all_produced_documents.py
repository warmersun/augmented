from typing import Optional

import chainlit as cl

from augmented import TeamLead


@cl.step(type="tool", name="List all produced documents")
def list_all_produced_documents() -> str:
  teamlead: Optional[TeamLead] = cl.user_session.get("teamlead")
  assert teamlead is not None, "teamlead should be set"
  if not teamlead.documents:
    return "No documents have been produced yet."
  d_retval = ', '.join(teamlead.documents.keys())
  return d_retval