# Augmented

A framework to assemble a team of "workers". This is an opnionated take on AI agents.
A worker is an AI augmented human. The AI can take over and automate 0-100%.

Each worker carries out a _task_: it receives some _inputs_ and has to deliver an _output_.
In the current implementation it's multiple inputs, single output. (If you need another output you can add another worker with similar instructions.)

These inputs and outputs are text based. Think: 📃 documents. 
It's set up such that there is a human readable part of each output created (in Markdown) as well as a structured JSON that is machine readable.

This way we can use AI assistants that are experts in the task, use custom tools and documents.

It is built on [OpenAI Assistants API](https://platform.openai.com/docs/assistants/overview) and [Chainlit](https://chainlit.io/)

## 👀 [demo](https://augmented-warmersun.replit.app/)

The demo is inspired by this post: [Why Talk to Customers When You Can Simulate Them? How artificial intelligence can help you understand what makes people tick - BY CHRIS SILVESTRI](https://every.to/p/decoding-your-customer-with-ai)

It has a 
- _marketer expert_ an AI that helps write marketing copy
- _persona simulator_ an AI that acts as if it were a person, characterized as a given persona and reacts to reading the marketing copy
- an _evaluator_ who then looks at all this and provides feedback to the marketer

One can run rounds of this cycle and hopefully iteratively improve the marketing copy.


## Goals

Right now the goal os the **augmented** framework is to allow quick experimentation with agentic workflows - mostly in the development environment - with the postential to then deploy the whole thing as a webapp.

To do this, one has to focus on editing the configuration file, which is a YAML.

Ther is a `planner` assistant that orchestrates and figures out what to do next...  
and then there are the `workers`...

You can list the inputs and the ouput for each `worker` and define the assistant (as in "OpenAI Assistant"),  
either by retrieving it by ID, or by writing the instructions, model and functions (which have to be built-in functions). There is one to fill the gap for OpenAI not offering _web search).

Workers can be set up to be full autonoumous, saying they have no user interaction and they can continue on the current thread or start a new one. Continuing the thread allows `observers` i.e. AI assistants that jump in, look at a back-and-forth conversation between another AI and the user and just provide their observations.

See the [config.yaml](.config.yaml) comments for more details.


