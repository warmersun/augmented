import json
import os
from typing import Optional

import chainlit as cl
from openai import AsyncAssistantEventHandler, AsyncOpenAI
from openai.types.beta import AssistantStreamEvent
from openai.types.beta.threads import Text, TextDelta
from openai.types.beta.threads.runs import ToolCall
from typing_extensions import override

from augmented import TeamLead
from function_tools import web_search_qa

# event handler for next user message

class MessageEventHandler(AsyncAssistantEventHandler):
    def __init__(self, author: str) -> None:
        super().__init__()
        self.author = author
        self.current_message: Optional[cl.Message] = None
        self.async_client = AsyncOpenAI(
          api_key=os.environ['OPENAI_API_KEY'],
        )
        
    @override
    async def on_text_created(self, text: Text) -> None:
        # remove the Finish button from the previous message
        previous_finish_actions = cl.user_session.get("finish_actions")
        if previous_finish_actions:
            for previous_finish_action in previous_finish_actions:
                await previous_finish_action.remove()

        self.current_message = await cl.Message(author=self.author, content="").send()
        # remember the new Finish button
        finish_actions =  [
            cl.Action(name="finish", value="finish", label="Finished", description="Indicate that the work is finished and the AI should now generate the output")
        ]
        cl.user_session.set("finish_actions", finish_actions)

    @override
    async def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
        assert self.current_message is not None, "current_message should be set before on_text_delta"
        await self.current_message.stream_token(delta.value or "")

    @override
    async def on_text_done(self, text: Text) -> None:
        # display a Finish button
        finish_actions = cl.user_session.get("finish_actions")
        if finish_actions:
            self.current_message.actions = finish_actions
            
        await self.current_message.update()
    
    @override
    async def on_tool_call_done(self, tool_call: ToolCall) -> None:
        if tool_call.type == "file_search":
            await show_file_search()               

    @override
    async def on_event(self, event: AssistantStreamEvent) -> None:
        # Retrieve events that are denoted with 'requires_action'
        # since these will have our tool_calls
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id  # Retrieve the run ID from the event data
            await self.handle_requires_action(event.data, run_id)

    async def handle_requires_action(self, data, run_id):
      tool_outputs = []

      for tool in data.required_action.submit_tool_outputs.tool_calls:
        if tool.function.name == "web_search_qa":
            arguments = json.loads(tool.function.arguments)
            tool_outputs.append({"tool_call_id": tool.id, "output": await web_search_qa(arguments['question'])})
        # Submit all tool_outputs at the same time
        await self.submit_tool_outputs(tool_outputs, run_id)

    async def submit_tool_outputs(self, tool_outputs, run_id):
      # Use the submit_tool_outputs_stream helper
      async with self.async_client.beta.threads.runs.submit_tool_outputs_stream(
        thread_id=self.current_run.thread_id,
        run_id=self.current_run.id,
        tool_outputs=tool_outputs,
        event_handler=MessageEventHandler(self.author),
      ) as stream:
        await stream.until_done()

async def ask_user_for_input(input_name: str) -> str:
    input_ask = await cl.AskUserMessage(content=f"Please provide the input {input_name}!", timeout=60).send()
    input = input_ask.get('output', 'No input provided') if input_ask else 'No input provided'
    return input

# helper to show the file search tool being used

@cl.step(type="tool", name="File Search")
async def show_file_search() -> None:
    pass

# event handler for output generation - where there is no user interaction

class OutputEventHandler(AsyncAssistantEventHandler):
    def __init__(self, author: str) -> None:
        super().__init__()
        self.author = author
        self.current_message: cl.Message = None

    @override
    async def on_text_created(self, text: Text) -> None:
        self.current_message = await cl.Message(author=self.author, content="Generating output...\n```").send()

    @override
    async def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
         await self.current_message.stream_token(delta.value or "")

    @override
    async def on_text_done(self, text: Text) -> None:
        await self.current_message.remove()

# lifecycle events

@cl.on_chat_start
async def start():
    teamlead = TeamLead(ask_user_for_input)
    cl.user_session.set("teamlead", teamlead)

    # show task list
    await show_task_list()

    worker = await teamlead.get_next_worker()
    cl.user_session.set("worker",worker)
    await task_running(worker.task)
    
    # the AI starts
    assert worker is not None, "worker should be set before calling start"
    assert worker.assistant is not None, "worker.assistant should be set before calling start"
    assert worker.assistant.name is not None, "worker.assistant.name should be set before calling start"
    if worker.has_user_interaction:
        await worker.get_next_assistant_message(MessageEventHandler(worker.assistant.name))
    else:
        await get_output()

@cl.on_stop
async def on_stop():
    # cancel-run is safe to call, even if the run is not running
    worker = cl.user_session.get("worker")
    await worker.cancel_run() if worker else None

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
        await worker.submit_user_message(message.content)
        await worker.get_next_assistant_message(MessageEventHandler(worker.assistant.name))    

async def save_output_and_start_next_worker() -> None:
    worker = cl.user_session.get("worker")
    assert worker is not None, "worker should be set before calling save_output_and_start_next_worker"
    
    teamlead = cl.user_session.get("teamlead")
    assert teamlead is not None, "teamlead should be set"
    teamlead.save_output()
    
    await task_done(worker.task)
    
    # get the next worker
    worker = await teamlead.get_next_worker()
    if worker is not None:
        await task_running(worker.task)
        cl.user_session.set("worker", worker)
        # the AI starts for the next worker
        if worker.has_user_interaction:
            await worker.get_next_assistant_message(MessageEventHandler(worker.assistant.name))
        else:
            await get_output()
    else:
        # no more workers
        await cl.Message(content="All done!").send()
        task_list = cl.user_session.get("task_list")
        assert task_list is not None, "task_list should be set"
        task_list.status = "Done"
        await task_list.update()

        
async def get_output():
    # get the worker from the user session
    worker = cl.user_session.get("worker")
    if worker is not None:
        
        # we ask the worker to generate the output and show it to the user to confirm
    
        msg = cl.Message(author=worker.assistant.name, content="")
        await msg.send()
    
        output = await worker.generate_output(OutputEventHandler(worker.assistant.name))

        try:
            output_parsed = json.loads(output)
            markdown = output_parsed.get("markdown", "No output generated")

            elements = [
                cl.Text(name="markdown", content=markdown, display="inline"),
                cl.Text(name="output", content=json.dumps(output_parsed, indent=4), display="side", language="javascript")
            ]

            if worker.has_user_interaction:
            # ask the user to confirm the output            
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
                msg.content ="Confirm the output is good to go!"
                msg.actions=actions
            else:
                msg.content ="Generated output:"
            # it always includes the elements: the markdown and the full output                
            msg.elements=elements
            await msg.update()

            if not worker.has_user_interaction:
                # the output is good to go
                await save_output_and_start_next_worker()

        except json.JSONDecodeError as e:
            msg.content = "Something went wrong with the output. Please try again."
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
            await save_output_and_start_next_worker()
                                
        else:        
            feedback = await cl.AskUserMessage(content="Please provide your feedback on the generated output!", timeout=30).send()
            feedback_str = feedback.get('output', 'Needs more work!') if feedback else 'Needs more work.'
            worker.output_needs_work(feedback_str)
            # we ask the worker to continue and return the next AI message to show
            await worker.get_next_assistant_message(MessageEventHandler(worker.assistant.name))
            
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
        await get_output()

    await action.remove()
    return "Finished! Generating output..."

# manage the task list that shows in the sidebar

async def show_task_list() -> None:
    teamlead = cl.user_session.get("teamlead")
    if teamlead is None:
        return
    task_list = cl.TaskList()
    task_list.status = "Running..."
    tasks = {}
    cl.user_session.set("task_list", task_list)
    for worker_name, worker_config in teamlead.config.items():
        task = cl.Task(title=f"{worker_name}: {worker_config['task']}")
        tasks[worker_config['task']] = task
        await task_list.add_task(task)

    cl.user_session.set("tasks", tasks)
    await task_list.send()

async def task_running(task_desc: str) -> None:
    task_list = cl.user_session.get("task_list")
    if task_list is None:
        return
    tasks = cl.user_session.get("tasks")
    if tasks is None:
        return
    task = tasks[task_desc]
    task.status = cl.TaskStatus.RUNNING
    await task_list.update()

async def task_done(task_desc: str) -> None:
    task_list = cl.user_session.get("task_list")
    if task_list is None:
        return
    tasks = cl.user_session.get("tasks")
    if tasks is None:
        return
    task = tasks[task_desc]
    task.status = cl.TaskStatus.DONE
    await task_list.update()  


if __name__ == "__main__":
  from chainlit.cli import run_chainlit
  run_chainlit(__file__)