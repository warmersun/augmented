A framework to assemble a team of "workers". This is an opnionated take on AI agents.
A worker is an AI augmented human. The AI can take over and automate 0-100%.


Each worker carries out a _task_: it receives some _inputs_ and has to deliver an _output_.
in the current implementation it's multiple inputs, single output. (If you need another output you can add another worker with similar instructions.)

These inputs and outputs are text based. Think: documents. 
It's sut up such that there is a human readable part of each output created (in Markdown) as well as a structured JSON that is machine readable.

This way we can use AI assistants that are experts in the task, use custom tools and documents.

It is build on [OpenAI Assistants API](https://platform.openai.com/docs/assistants/overview) and [Chainlit](https://chainlit.io/)

See [demo](https://augmented-warmersun.replit.app/)

- Worker 1 is an **assistant**: assisants can be defined in the configuraiton by writing instructions or it can be set up in the [OpenAI platform[(https://platform.openai.com/playground/assistants)] and referenced by ID
- Observer 1 is an **observer**: it can look at the "thread" between the human user and the AI assistant from the previous worker (Worker 1, in this case) and produce some output without any user interaction. It provides some constructive criticism. It could be some other self-evaluation or summary.
- Worker 2 demonstrates function calling. It gets some up-to-date info on recent developments using Perplexity API
- Worker 3 finishes of writing a story. It uses all previous outputs produced.
