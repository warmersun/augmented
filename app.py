import os

import chainlit as cl
from openai import AsyncAssistantEventHandler, OpenAI
from openai.types.beta.threads import Text, TextDelta
from typing_extensions import override

from augmented import Worker
from augmented.observer import Observer


class EventHandler(AsyncAssistantEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self.current_message: cl.Message = None
        
    @override
    async def on_text_created(self, text: Text) -> None:
        # remove the Finish button from the previous message
        previous_finish_actions = cl.user_session.get("finish_actions")
        if previous_finish_actions:
            for previous_finish_action in previous_finish_actions:
                await previous_finish_action.remove()

        self.current_message = await cl.Message(content="").send()
        # remember the new Finish button
        finish_actions =  [
            cl.Action(name="finish", value="finish", label="Finished", description="Indicate that the work is finished and the AI should now generate the output")
        ]
        cl.user_session.set("finish_actions", finish_actions)

    @override
    async def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
         await self.current_message.stream_token(delta.value or "")

    @override
    async def on_text_done(self, text: Text) -> None:
        # display a Finish button
        finish_actions = cl.user_session.get("finish_actions")
        if finish_actions:
            self.current_message.actions = finish_actions
            
        await self.current_message.update()
        
@cl.on_chat_start
async def start():
    client = OpenAI(
         api_key=os.environ['OPENAI_API_KEY'],
    ) 
    assistant =  client.beta.assistants.create(
      name="Content Worker",
      instructions=
        "You are a content creator assistant."
        "You work together with the user - the facilitator - to create lesson content for the learning goals specified in the input. This is not an entire lesson plan just content to be used in one: stories, fun facts, elements to be used by a facilitator."
        "Make sure the content is fun, interesting for students who are high school juniors."
        "Input: learning goals. "
        "Output: content for a each learning goal that the facilitator can later use to build out their lesson plan.",
      model="gpt-4o",
    )
    learning_goal = await cl.AskUserMessage(content="Please provide the learning goal!", timeout=30).send()
    learning_goal_str = learning_goal.get('output', 'fun facts about Lenin') if learning_goal else 'fun facts about Lenin'

    worker =  Worker(assistant, f"Learning goal: {learning_goal_str}")
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
            await get_output()
        else:
            await worker.get_next_assistant_message(EventHandler())    

async def get_output():
    # get the worker from the user session
    worker = cl.user_session.get("worker")
    if worker is not None:
        
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
                value="needs_more_work", 
                label="Needs more work...", 
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

            # ***
            # Let's try an observer!
            # observe the output
            client = OpenAI(
                 api_key=os.environ['OPENAI_API_KEY'],
            ) 
            observer_assistant = client.beta.assistants.create(
              name = "Content Observer",
              instructions = 
                "You are an observer. You look at conversations between an AI content creator assistant and a facilitator and evaluate it with constructive criticism."
                " Is this content something that a bored-out-of-their-maind high school junir would be interested in?"
                " Your job is not to help the user or answer their questions but to observe and analyze the entire conversation. "
                " Provide your analysis! Output as JSON structure containing an `observation` string",
              model="gpt-4o",
            )
            observer = Observer(observer_assistant, worker.input, worker.output, worker.thread)
            observation = observer.observe()
            await cl.Message(content=f"Observation: {observation}").send()
            # ***
        else:        
            feedback = await cl.AskUserMessage(content="Please provide your feedback on the generated output!", timeout=30).send()
            feedback_str = feedback.get('output', 'Needs more work!') if feedback else 'Needs more work.'
            worker.output_needs_work(feedback_str)
            # we ask the worker to continue and return the next AI message to show
            await worker.get_next_assistant_message(EventHandler())
            
        # remove the action buttons from the UI
        actions = cl.user_session.get("actions")
        if actions is not None:
            for action in actions:
                await action.remove()

    return "Confirmed!"

@cl.action_callback("finish")
async def finish(action: cl.Action):
    worker = cl.user_session.get("worker")
    if worker is not None and action.value == "finish":
        worker.finish()
        await get_output()

    await action.remove()
    return "Finished! Generating output..."

if __name__ == "__main__":
  from chainlit.cli import run_chainlit
  run_chainlit(__file__)