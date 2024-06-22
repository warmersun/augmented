import json

import chainlit as cl
from openai import AsyncAssistantEventHandler
from openai.types.beta import AssistantStreamEvent
from openai.types.beta.threads import Text, TextDelta
from openai.types.beta.threads.runs import ToolCall, ToolCallDelta
from typing_extensions import override

from augmented import Observer, TeamLead, Worker


class EventHandler(AsyncAssistantEventHandler):
    def __init__(self, author: str) -> None:
        super().__init__()
        self.author = author
        self.current_message: cl.Message = None
        
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
        pass

async def ask_user_for_input(input_name: str) -> str:
    input_ask = await cl.AskUserMessage(content=f"Please provide the input {input_name}!", timeout=60).send()
    input = input_ask.get('output', 'No input provided') if input_ask else 'No input provided'
    return input

@cl.step(type="tool", name="File Search")
async def show_file_search() -> None:
    pass

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
    await worker.get_next_assistant_message(EventHandler(worker.assistant.name))

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
        task = cl.Task(title=f"{worker_config['task']}")
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
            await worker.get_next_assistant_message(EventHandler(worker.assistant.name))    

async def get_output():
    # get the worker from the user session
    worker = cl.user_session.get("worker")
    if worker is not None:
        
        # we ask the worker to generate the output and show it to the user to confirm
    
        msg = cl.Message(author=worker.assistant.name, content="")
        await msg.send()
    
        output = await worker.generate_output(OutputEventHandler(worker.assistant.name))
        output_parsed = json.loads(output)
        markdown = output_parsed.get("markdown", "No output generated")
        
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
            cl.Text(name="markdown", content=markdown, display="inline"),
            cl.Text(name="output", content=output, display="side", language="javascript")
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
            # TODO: do we need this?
            worker.output_is_good_to_go()

            teamlead = cl.user_session.get("teamlead")
            teamlead.save_output()
            
            # check if the worker has an observer
            observer = teamlead.get_observer()

            if observer is not None:            
                output = await observer.observe(OutputEventHandler(observer.assistant.name))
                output_parsed = json.loads(output)
                markdown = output_parsed.get("markdown", "No output generated")

                await cl.Message(
                    content="Observation: ", 
                    elements = [
                        cl.Text(name="markdown", content=markdown, display="inline"),
                        cl.Text(name="output", content=output, display="side", language="javascript")
                    ]
                ).send()

            await task_done(worker.task)

            # get the next worker
            worker = await teamlead.get_next_worker()
            await task_running(worker.task)
            cl.user_session.set("worker", worker)
            
            # the AI starts for the next worker
            await worker.get_next_assistant_message(EventHandler(worker.assistant.name))
                                
        else:        
            feedback = await cl.AskUserMessage(content="Please provide your feedback on the generated output!", timeout=30).send()
            feedback_str = feedback.get('output', 'Needs more work!') if feedback else 'Needs more work.'
            worker.output_needs_work(feedback_str)
            # we ask the worker to continue and return the next AI message to show
            await worker.get_next_assistant_message(EventHandler(worker.assistant.name))
            
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