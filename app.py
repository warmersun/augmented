import os

import chainlit as cl
from openai import AsyncAssistantEventHandler, OpenAI
from openai.types.beta.threads import Text, TextDelta
from typing_extensions import override

from augmented import Worker


class EventHandler(AsyncAssistantEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.current_message: cl.Message = None
        
    @override
    async def on_text_created(self, text: Text) -> None:
        self.current_message = await cl.Message(content="").send()

    @override
    async def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
         await self.current_message.stream_token(delta.value or "")

    @override
    async def on_text_done(self, text: Text) -> None:
        await self.current_message.update()
        
@cl.on_chat_start
async def start():
    client = OpenAI(
         api_key=os.environ['OPENAI_API_KEY'],
    ) 
    assistant =  client.beta.assistants.create(
      name="Content Worker",
      instructions=
        "You are a content creator assistant." \
        "You work together with the user - the facilitator - to create lesson content for the learning goals specified in the input. " \
        "Make sure the content is fun, interesting for students who are high school juniors."
        "Input: learning goals. " \
        "Output: content for a each learning goal that the facilitator can later use to build out their lesson plan. " \
        "When you think you're done and have everything to create the output remind the user to say 'FINISHED'.",
      model="gpt-4o",
    )
    worker =  Worker(assistant, "Learning goal: Great October Revolution in 1917. The student should know about Lenin, the tsar and why peoplpe revolted, just the basics.")
    cl.user_session.set("worker",worker)
    # the AI starts
    await worker.get_next_assistant_message(EventHandler())

@cl.on_message
async def main(message: cl.Message):
    # the user has just submitted a message...     
    # so what do we do?
    # we need to get the worker from the user session
    # then we let the worker know about the message
    # then we check if this message means that the user has finished and the job is completed
    # if so, we ask the worker to generate the output and show it to the user to confirm
    # if not, we ask the worker to continue and return the next AI message to show 
    # NOTE: this will be more complicated with function calls, tool use, streaming

    # get the worker from the user session
    worker = cl.user_session.get("worker")
    if worker is not None:
        # let the worker know about the message
        worker.submit_user_message(message.content)
        #  check if this message means that the user has finished and the job is completed
        if worker.is_finished():
            # we ask the worker to generate the output and show it to the user to confirm

            msg = cl.Message(content="")
            await msg.send()
            
            output = worker.generate_output()
            actions = [
                # confirm
                cl.Action(
                    name='confirm_output', 
                    value="confirm", 
                    label="Confirm", 
                    description="Confirm the output is good to go."
                ),
                # cancel
                cl.Action(
                    name='confirm_output', 
                    value="cancel", 
                    label="Cancel", 
                    description="Need to keep working on the output."
                )
            ]
            cl.user_session.set("actions", actions)
            elements = [
                cl.Text(name="output", content=output, display="inline")
            ]

            
            msg.content ="Confirm the output is good to go!"
            msg.actions=actions
            msg.elements=elements
            await msg.update()
        else:
            await cl.Message(
                content=await worker.get_next_assistant_message(EventHandler())                
            ).send()

@cl.action_callback("confirm_output")
async def confirm_output(action: cl.Action):
    # after the user or the AI has decided that the job is complete the AI generated the output and presented it for the user.
    # the user was asked to confirm that the output is good to go
    # we need to let the worker know whether the output is good to go now and thejob is finished or that they need to keep working on it

    # get the worker from the user session
    worker = cl.user_session.get("worker")
    if worker is not None:
        # let the worker know 
        if action.value == "confirm":              
            worker.output_is_good_to_go()
        else:        
            worker.output_needs_work()
            # we ask the worker to continue and return the next AI message to show
            await cl.Message(
                content = await worker.get_next_assistant_message()
            ).send()
        # remove the action buttons from the UI
        actions = cl.user_session.get("actions")
        if actions is not None:
            for action in actions:
                await action.remove()

    return "Confirmed!"

if __name__ == "__main__":
  from chainlit.cli import run_chainlit
  run_chainlit(__file__)