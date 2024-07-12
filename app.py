import json
import os
from typing import Optional

import chainlit as cl
from chainlit.message import AskUserMessage
from openai import AsyncAssistantEventHandler, AsyncOpenAI
from openai.types.beta import AssistantStreamEvent
from openai.types.beta.threads import Message, Text, TextDelta
from openai.types.beta.threads.runs import ToolCall
from typing_extensions import override

from augmented import TeamLead
from function_tools import (
    display_document,
    get_document,
    list_all_produced_documents,
    set_document,
    web_search_brave,
    web_search_qa_perplexity,
)
from license_management import (
    check_and_store_license_key,
    get_license_key,
    verify_license,
)

with open('LICENSE_KEY_HOW_TO.md', 'r') as file:
    LICENSE_KEY_HOW_TO = file.read()

# event handler for next user message

class WorkerMessageEventHandler(AsyncAssistantEventHandler):

    def __init__(self) -> None:
        super().__init__()
        self.current_message: Optional[cl.Message] = None
        self.async_client = AsyncOpenAI(api_key=os.environ['OPENAI_API_KEY'], )

    @override
    async def on_text_created(self, text: Text) -> None:
        # remove the Finish button from the previous message
        previous_finish_actions = cl.user_session.get("finish_actions")
        if previous_finish_actions:
            for previous_finish_action in previous_finish_actions:
                await previous_finish_action.remove()

        worker = cl.user_session.get("worker")
        assert worker is not None, "Worker not found in session."
        assert worker.assistant is not None, "Worker assistant not found in session." 
        self.current_message = await cl.Message(author=worker.assistant.name,
                                                content="").send()
        # remember the new Finish button
        finish_actions = [
            cl.Action(
                name="finish",
                value="finish",
                label="👍 Finished",
                description=
                "Indicate that the work is finished and the AI should now generate the output"
            )
        ]
        cl.user_session.set("finish_actions", finish_actions)

    @override
    async def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
        assert self.current_message is not None, "current_message should be set before on_text_delta"
        await self.current_message.stream_token(delta.value or "")

#    @override
#    async def on_text_done(self, text: Text) -> None:
#        assert self.current_message is not None, "current_message should be set before on_text_done"
#        # display a Finish button
#        finish_actions = cl.user_session.get("finish_actions")
#        if finish_actions:
#            self.current_message.actions = finish_actions
#
#        await self.current_message.update()

    @override
    async def on_message_done(self, message: Message) -> None:
        assert len(message.content) ==1, "Message should have exactly one content"
        if message.content[0].type == "text":
            message_content = message.content[0].text
            annotations = message_content.annotations
            citations = []
            for index, annotation in enumerate(annotations):
                message_content.value = message_content.value.replace(annotation.text, f" [{index}]")
                file_citation = getattr(annotation, "file_citation", None)
                if file_citation:
                    cited_file = await self.async_client.files.retrieve(file_citation.file_id)
                    citations.append(f"[{index}] {cited_file.filename}[{annotation.start_index}:{annotation.end_index}]")
            assert self.current_message is not None, "current_message should be set before on_message_done"
            self.current_message.content = f"{message_content.value}" + "\n\n---\n\n" + "\n".join(citations)
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
            if tool.function.name == "web_search_qa_perplexity":
                arguments = json.loads(tool.function.arguments)
                tool_outputs.append({
                    "tool_call_id":
                    tool.id,
                    "output":
                    await web_search_qa_perplexity(arguments['question'])
                })
            elif tool.function.name == "web_search_brave":
                args = json.loads(tool.function.arguments)
                if "freshness" in args:
                    output = await web_search_brave(args["q"], freshness=args["freshness"])
                else:
                    output = await web_search_brave(args["q"])
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": json.dumps(output)
                })
        # Submit all tool_outputs at the same time
        await self.submit_tool_outputs(tool_outputs, run_id)

    async def submit_tool_outputs(self, tool_outputs, run_id):
        # Use the submit_tool_outputs_stream helper
        assert self.current_run is not None, "self.current_run should be set before calling submit_tool_outputs"
        async with self.async_client.beta.threads.runs.submit_tool_outputs_stream(
                thread_id=self.current_run.thread_id,
                run_id=run_id,
                tool_outputs=tool_outputs,
                event_handler=WorkerMessageEventHandler(),
        ) as stream:
            await stream.until_done()


async def ask_user_for_input(input_name: str) -> str:
    input_ask = await cl.AskUserMessage(
        author="teamlead",
        content=f"Please provide the input {input_name}!", timeout=60).send()
    input = input_ask.get(
        'output', 'No input provided') if input_ask else 'No input provided'
    return input


# helper to show the file search tool being used


@cl.step(type="tool", name="File Search")
async def show_file_search() -> None:
    pass


# event handler for output generation - where there is no user interaction


class WorkerOutputEventHandler(AsyncAssistantEventHandler):

    def __init__(self) -> None:
        super().__init__()
        self.current_message: Optional[cl.Message] = None

    @override
    async def on_text_created(self, text: Text) -> None:
        worker = cl.user_session.get("worker")
        assert worker is not None, "Worker not found in session."
        assert worker.assistant is not None, "Worker assistant not found in session." 
        self.current_message = await cl.Message(
            author=worker.assistant.name, content="Generating output...\n```").send()

    @override
    async def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
        assert self.current_message is not None, "current_message should be set before on_text_delta"
        await self.current_message.stream_token(delta.value or "")

    @override
    async def on_text_done(self, text: Text) -> None:
        assert self.current_message is not None, "current_message should be set before on_text_done"
        await self.current_message.remove()


# event hander for user messages of the planner


class PlannerMessageEventHandler(AsyncAssistantEventHandler):

    def __init__(self) -> None:
        super().__init__()
        self.author = "planner"
        self.current_message: Optional[cl.Message] = None
        self.async_client = AsyncOpenAI(api_key=os.environ['OPENAI_API_KEY'], )

    @override
    async def on_text_created(self, text: Text) -> None:
        self.current_message = await cl.Message(author=self.author,
                                                content="").send()

    @override
    async def on_text_delta(self, delta: TextDelta, snapshot: Text) -> None:
        assert self.current_message is not None, "current_message should be set before on_text_delta"
        await self.current_message.stream_token(delta.value or "")

    @override
    async def on_text_done(self, text: Text) -> None:
        assert self.current_message is not None, "current_message should be set before on_text_done"
        await self.current_message.update()

    @override
    async def on_event(self, event: AssistantStreamEvent) -> None:
        # Retrieve events that are denoted with 'requires_action'
        # since these will have our tool_calls
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id  # Retrieve the run ID from the event data
            await self.handle_requires_action(event.data, run_id)

    async def handle_requires_action(self, data, run_id):
        tool_outputs = []
        worker = None
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "get_document":
                arguments = json.loads(tool.function.arguments)
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": get_document(arguments['document_name'])
                })
            elif tool.function.name == "set_document":
                arguments = json.loads(tool.function.arguments)
                # make sure arguments['document_json'] is a string
                if not isinstance(arguments['document_json'], str):
                    arguments['document_json'] = json.dumps(arguments['document_json'], indent=4)
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": await set_document(arguments['document_name'], arguments['document_json'])
                })
            elif tool.function.name == "display_document":
                arguments = json.loads(tool.function.arguments)
                # make sure arhuments['document_json'] is a string
                if not isinstance(arguments['document_json'], str):
                    arguments['document_json'] = json.dumps(arguments['document_json'], indent=4)
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": await display_document(arguments['document_json'])
                })
            elif tool.function.name == "list_all_procuded_documents":
                # arguments = json.loads(tool.function.arguments) -- doesn't take any arguments
                tool_outputs.append({
                    "tool_call_id": tool.id,
                    "output": list_all_produced_documents()
                })
            elif tool.function.name == "choose_next_worker":
                arguments = json.loads(tool.function.arguments)
                res = await cl.AskActionMessage(
                    author=self.author,
                    content=f"Use the {arguments['worker_name']} worker?",
                    actions=[
                        cl.Action(name="continue", value="ok", label="✅ OK"),
                        cl.Action(name="cancel",
                                  value="cancel",
                                  label="❌ Cancel"),
                    ],
                    timeout=5
                ).send()
                if res is None or res.get("value") == "ok":
                    teamlead = cl.user_session.get("teamlead")
                    assert teamlead is not None, "teamlead should be set"
                    worker = await teamlead.get_worker(
                        arguments['worker_name'], WorkerMessageEventHandler,
                        WorkerOutputEventHandler)
                    # show which worker is being used in the task list
                    await task_running(worker.task)
                    cl.user_session.set("worker", worker)
                    cl.user_session.set("current_team_member", worker)
                    tool_outputs.append({
                        "tool_call_id":
                        tool.id,
                        "output":
                        f"Use of worker {arguments['worker_name']} as next step is confirmed."
                    })
                else:
                    tool_outputs.append({
                        "tool_call_id":
                        tool.id,
                        "output":
                        f"Use of worker {arguments['worker_name']} is cancelled."
                    })
        # Submit all tool_outputs at the same time
        await self.submit_tool_outputs(tool_outputs, run_id)
        # let's kick off the next step
        if worker is not None:
            if worker.has_user_interaction:
                await worker.get_next_assistant_message()
            else:
                await finished_get_output()

    async def submit_tool_outputs(self, tool_outputs, run_id):
        teamlead = cl.user_session.get("teamlead")
        assert teamlead is not None, "teamlead should be set"
        # Debug logging to trace the issue
        for tool_output in tool_outputs:
            assert isinstance(tool_output['output'], str), f"Expected string but got {type(tool_output['output'])} in {tool_output}"
            
        # Use the submit_tool_outputs_stream helper
        async with self.async_client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=teamlead.planner_thread.id,
            run_id=run_id,
            tool_outputs=tool_outputs,
            event_handler=PlannerMessageEventHandler(),
        ) as stream:
            await stream.until_done()


# lifecycle events


@cl.on_chat_start
async def start():
    user = cl.user_session.get("user")
    assert user is not None, "User not found in session."
    license_key = await get_license_key(user.identifier)
    while not license_key:
        res = await AskUserMessage(content=LICENSE_KEY_HOW_TO, timeout=300).send()
        license_key = res.get('output') if res else None
        if license_key:
            is_valid = await check_and_store_license_key(license_key, user.identifier)
            if not is_valid:
                license_key = None
    cl.user_session.set("license_key", license_key)
    
    teamlead = TeamLead(ask_user_for_input)
    cl.user_session.set("teamlead", teamlead)
    # display the task list
    await show_task_list()
    # start with the planner
    planner = await teamlead.get_planner(PlannerMessageEventHandler)
    cl.user_session.set("planner", planner)
    cl.user_session.set("current_team_member", planner)
    # the AI starts
    await planner.get_next_assistant_message()


@cl.on_stop
async def on_stop():
    # cancel-run is safe to call, even if the run is not running
    current_team_member = cl.user_session.get("current_team_member")
    await current_team_member.cancel_run() if current_team_member else None

@cl.on_chat_end
async def end():
    # call delete any assistant created by the teamlead
    teamlead = cl.user_session.get("teamlead")
    assert teamlead is not None, "teamlead should be set"
    await teamlead.delete_any_assistant_created()
    
@cl.on_message
async def main(message: cl.Message):
    # the user has just submitted a message...
    # so what do we do?
    # we need to get the worker or planner from the user session
    # then we let it know about the message

    # get the worker from the user session
    current_team_member = cl.user_session.get("current_team_member")
    if current_team_member is not None:
        # let the worker know about the message
        await current_team_member.submit_user_message(message.content)
        await current_team_member.get_next_assistant_message()


async def save_output_and_continue_planner() -> None:
    worker = cl.user_session.get("worker")
    assert worker is not None, "worker should be set before calling save_output_and_continue_planner"
    if worker.task is not None:
        await task_done(worker.task)
    teamlead = cl.user_session.get("teamlead")
    assert teamlead is not None, "teamlead should be set"
    teamlead.save_output()
    planner = cl.user_session.get("planner")
    assert planner is not None, "planner should be set"
    # note: this message is not displayed on the UI
    await planner.submit_user_message(f"I have just finished using the {worker.name} worker and produced the {worker.output_name} deliverable output.")
    cl.user_session.set("current_team_member", planner)
    await planner.get_next_assistant_message()


async def finished_get_output() -> None:
    # check license and increment counter
    license_key = cl.user_session.get("license_key")
    assert license_key is not None, "license_key should be set"
    good, uses = await verify_license(license_key)
    if not good:
        await cl.Message(
            author="System", 
            content="Your license key is no longer valid. Please contact your team lead to get a new one."
        ).send()
        return
    await show_license_usage(uses, int(os.environ['GUMROAD_MAX_USES']))
        
    # get the worker from the user session
    worker = cl.user_session.get("worker")
    if worker is not None:

        # we ask the worker to generate the output and show it to the user to confirm

        msg = cl.Message(author=worker.assistant.name, content="")
        await msg.send()

        output = await worker.generate_output()

        try:
            output_parsed = json.loads(output)
            markdown = output_parsed.get("markdown", "No output generated")

            elements = [
                cl.Text(name="markdown", content=markdown, display="inline"),
                cl.Text(name="output",
                        content=json.dumps(output_parsed, indent=4),
                        display="side",
                        language="javascript")
            ]

            if worker.has_user_interaction:
                # ask the user to confirm the output
                actions = [
                    # confirm
                    cl.Action(name='confirm_output',
                              value="confirm",
                              label="✅ Confirm",
                              description="Confirm the output is good to go."),
                    # cancel
                    cl.Action(
                        name='confirm_output',
                        value="needs_more_work",
                        label="🛠 Needs more work...",
                        description="Need to keep working on the output.")
                ]
                cl.user_session.set("actions", actions)
                msg.content = "Confirm the output is good to go!"
                msg.actions = actions
            else:
                msg.content = "Generated output:"
            # it always includes the elements: the markdown and the full output
            msg.elements = elements
            await msg.update()

            if not worker.has_user_interaction:
                # the output is good to go
                await save_output_and_continue_planner()

        except json.JSONDecodeError:
            msg.content = "Something went wrong with the output. Please try again."
            msg.elements = [
                cl.Text(name="output", content=f"```\n{output}\n```\n", display="inline", language="markdown")
            ]
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
            await save_output_and_continue_planner()

        else:
            feedback = await cl.AskUserMessage(
                author=worker.assistant.name,
                content="Please provide your feedback on the generated output!",
                timeout=30).send()
            feedback_str = feedback.get(
                'output',
                'Needs more work!') if feedback else 'Needs more work.'
            worker.output_needs_work(feedback_str)
            # we ask the worker to continue and return the next AI message to show
            await worker.get_next_assistant_message()

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
        await finished_get_output()

    await action.remove()
    return "Finished! Generating output..."


# manage the task list that shows in the sidebar


async def show_task_list() -> None:
    teamlead = cl.user_session.get("teamlead")
    if teamlead is None:
        return
    task_list = cl.TaskList()
    tasks = {}
    for worker_name, worker_config in teamlead.config['workers'].items():
        if worker_config.get("task") is not None:
            if worker_config.get('has_user_interaction', True):
                icon = "👩‍🏭"
            else:
                icon = "🤖"
            task = cl.Task(
                title=f"{icon} {worker_name}: {worker_config['task']}")
            tasks[worker_config['task']] = task
            await task_list.add_task(task)
    if tasks:
        cl.user_session.set("tasks", tasks)
        await task_list.send()
        cl.user_session.set("task_list", task_list)


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

async def show_license_usage(uses: int, max_uses: int) -> None:
    task_list = cl.user_session.get("task_list")
    if task_list is None:
        return
    task_list.status = f"License usage: {uses}/{max_uses}"
    await task_list.update()

@cl.oauth_callback
def oauth_callback(
  provider_id: str,
  token: str,
  raw_user_data: dict[str, str],
  default_user: cl.User,
) -> Optional[cl.User]:
  return default_user

if __name__ == "__main__":
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)
    