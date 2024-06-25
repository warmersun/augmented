def json_mode_instruction_ending(output_or_observation: str = "output") -> str:
  return f"Generate the {output_or_observation}. Remember, the {output_or_observation} is a JSON object. " \
         f"Use JSON structure as you see fit. The goal is to make it machine readable. " \
         f"It must include the key 'markdown' at the root level with the value being the full text of the {output_or_observation} in Markdown format. " \
         f"This `markdown` field will be used to present the {output_or_observation} to the user; whereas the entire JSON structure will be used by other AI assistants as input."
