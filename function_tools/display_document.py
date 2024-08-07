import json

import chainlit as cl


@cl.step(type="tool", name="Display document")
async def display_document(document_json: str) -> str:
  msg = cl.Message(content="Displaying document output...")
  await msg.send()
  try:
    document = json.loads(document_json)
    markdown = document.get("markdown", "No output generated")
    elements = [
        cl.Text(name="markdown", content=markdown, display="inline"),
        cl.Text(name="output",
                content=json.dumps(document, indent=4),
                display="side",
                language="javascript")
    ]
    msg.elements = elements
  except json.JSONDecodeError as e:
    elements = [
      cl.Text(name="document_json", content=f"```\n{document_json}\n```\n", display="inline"),
    ]
    msg.elements = elements
  finally:
    await msg.update()
  return "Displayed the document."