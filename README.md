
# projectdavid — Python SDK

[![PyPI](https://img.shields.io/pypi/v/projectdavid)](https://pypi.org/project/projectdavid/)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](https://polyformproject.org/licenses/noncommercial/1.0.0/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Lint, Test, Tag, Publish Status](https://github.com/frankie336/projectdavid/actions/workflows/test_tag_release.yml/badge.svg)](https://github.com/frankie336/projectdavid/actions/workflows/test_tag_release.yml)

The `projectdavid` package is the Python SDK for Project David.

It provides Python interfaces for working with Project David resources including assistants, threads, messages, runs, inference streams, tools, files, vector stores, and Scratchpads.

The SDK communicates with a running Project David platform instance and provides validated client objects over the platform HTTP APIs.

---

## Installation

```bash
pip install projectdavid
```

Requirements:

```text
Python 3.10+
A running Project David platform instance
A Project David API key
```

---

## Client

Create an SDK client with `Entity`:

```python
import os

from dotenv import load_dotenv
from projectdavid import Entity

load_dotenv()

client = Entity(
    base_url=os.getenv("BASE_URL"),
    api_key=os.getenv("PROJECTDAVID_API_KEY"),
)
```

`PROJECTDAVID_API_KEY` authenticates the SDK client against the Project David platform.

`BASE_URL` identifies the Project David API endpoint.

A local platform deployment commonly exposes the API at:

```text
http://localhost:80
```

---

## SDK Resources

`Entity` exposes resource clients for the major Project David API surfaces.

Typical interfaces include:

```text
client.assistants
client.threads
client.messages
client.runs
client.files
client.vector_stores
client.scratchpads
client.tools
client.synchronous_inference_stream
```

These clients provide Python methods over the corresponding platform resources.

---

## Quick Start

```python
import os

from dotenv import load_dotenv
from projectdavid import Entity

load_dotenv()

client = Entity(
    base_url=os.getenv("BASE_URL"),
    api_key=os.getenv("PROJECTDAVID_API_KEY"),
)

# ------------------------------------------------------------------
# Create an assistant
# ------------------------------------------------------------------

assistant = client.assistants.create_assistant(
    name="my_assistant",
    instructions="You are a helpful AI assistant.",
)

# ------------------------------------------------------------------
# Create a thread
# ------------------------------------------------------------------

thread = client.threads.create_thread()

# ------------------------------------------------------------------
# Add a user message
# ------------------------------------------------------------------

message = client.messages.create_message(
    thread_id=thread.id,
    role="user",
    content="Tell me about the latest trends in AI.",
    assistant_id=assistant.id,
)

# ------------------------------------------------------------------
# Create a run
# ------------------------------------------------------------------

run = client.runs.create_run(
    assistant_id=assistant.id,
    thread_id=thread.id,
)

# ------------------------------------------------------------------
# Configure inference
# ------------------------------------------------------------------

stream = client.synchronous_inference_stream

stream.setup(
    user_id=os.getenv("ENTITIES_USER_ID"),
    thread_id=thread.id,
    assistant_id=assistant.id,
    message_id=message.id,
    run_id=run.id,
    api_key=os.getenv("PROVIDER_API_KEY"),
)

# ------------------------------------------------------------------
# Stream the response
# ------------------------------------------------------------------

for chunk in stream.stream_chunks(
    model="hyperbolic/deepseek-ai/DeepSeek-V3-0324",
    timeout_per_chunk=15.0,
):
    content = chunk.get("content", "")

    if content:
        print(content, end="", flush=True)
```

See the [Quick Start guide](https://docs.projectdavid.co.uk/docs/sdk-quick-start) for the event-driven interface, tool calling, and additional usage examples.

---

## Authentication

Project David distinguishes between platform authentication and model-provider authentication.

```text
PROJECTDAVID_API_KEY
    → authenticates the SDK against Project David

PROVIDER_API_KEY
    → authenticates inference against the configured model provider
```

For example:

```python
client = Entity(
    api_key=os.getenv("PROJECTDAVID_API_KEY"),
)
```

and separately:

```python
stream.setup(
    user_id=os.getenv("ENTITIES_USER_ID"),
    thread_id=thread.id,
    assistant_id=assistant.id,
    message_id=message.id,
    run_id=run.id,
    api_key=os.getenv("PROVIDER_API_KEY"),
)
```

These credentials serve different roles and should not be treated as interchangeable.

---

## Assistants

Assistants define model configuration, instructions, and available tools.

```python
assistant = client.assistants.create_assistant(
    name="research_assistant",
    model="gpt-oss-120b",
    instructions="Research the requested topic and report your findings.",
)
```

Platform tools can be attached through the assistant tool definition.

For example:

```python
assistant = client.assistants.create_assistant(
    name="research_assistant",
    model="gpt-oss-120b",
    instructions="Research the requested topic and record useful findings.",
    tools=[
        {"type": "web_search"},
        {"type": "scratch_pad"},
    ],
)
```

The full platform-tool definitions are resolved by the runtime.

---

## Threads

Threads provide persistent conversational state.

```python
thread = client.threads.create_thread()
```

A thread can be used across multiple messages and runs.

---

## Messages

Messages are created against threads.

```python
message = client.messages.create_message(
    thread_id=thread.id,
    role="user",
    content="Explain the current architecture.",
    assistant_id=assistant.id,
)
```

Messages provide the conversational input associated with a run.

---

## Runs

Runs associate an assistant with a thread for an inference operation.

```python
run = client.runs.create_run(
    assistant_id=assistant.id,
    thread_id=thread.id,
)
```

The returned run ID is used when configuring inference and correlating streamed events.

---

## Streaming

Project David exposes inference as a structured stream.

The SDK supports both lower-level chunk streaming and typed event streaming.

A stream is configured with:

```python
stream = client.synchronous_inference_stream

stream.setup(
    user_id=os.getenv("ENTITIES_USER_ID"),
    thread_id=thread.id,
    assistant_id=assistant.id,
    message_id=message.id,
    run_id=run.id,
    api_key=os.getenv("PROVIDER_API_KEY"),
)
```

Chunk-based consumption:

```python
for chunk in stream.stream_chunks(
    model="hyperbolic/deepseek-ai/DeepSeek-V3-0324",
    timeout_per_chunk=15.0,
):
    print(chunk)
```

The event-driven interface exposes structured events for different parts of the inference lifecycle.

Depending on the run, these can include:

```text
ContentEvent
ReasoningEvent
StatusEvent
ResearchStatusEvent
WebStatusEvent
ScratchpadEvent
ToolCallRequestEvent
GeneratedFileEvent
```

See the [Stream Contract](https://docs.projectdavid.co.uk/docs/sdk-stream-contract) for the current wire and SDK event definitions.

---

## Platform Tools

Project David includes runtime-managed tools that can be attached to assistants.

Examples include:

```text
web_search
scratch_pad
code_interpreter
computer
file_search
deep_research
```

A tool can be declared using its placeholder definition:

```python
assistant = client.assistants.create_assistant(
    name="tool_assistant",
    model="gpt-oss-120b",
    instructions="Use the available tools when required.",
    tools=[
        {"type": "code_interpreter"},
    ],
)
```

The runtime expands the placeholder into the full platform tool definition when the run is executed.

---

## Function Calling

Assistants can also use application-defined function tools.

Function tools allow the model to request operations implemented by the application rather than by the Project David platform itself.

See the [Function Calls documentation](https://docs.projectdavid.co.uk/docs/12_sdk-function-calls) for the tool schema and execution flow.

---

## MCP Tools

Project David supports MCP-backed tools through the SDK and orchestration runtime.

MCP tools are discovered and executed through the platform tool infrastructure while preserving the normal Project David run and streaming model.

See the SDK MCP documentation for the current registration and execution interfaces.

---

## Scratchpads

The SDK exposes Scratchpads as first-class resources.

```python
scratchpad = client.scratchpads.create_scratchpad(
    thread_id=thread.id,
)
```

Scratchpads provide persistent working state associated with a thread.

The resource client includes operations for:

```text
create_scratchpad
retrieve_scratchpad
retrieve_scratchpad_by_thread
list_scratchpads
update_scratchpad
delete_scratchpad

get_content
set_content
clear_content

append_entry
list_entries
clear_entries

clear_scratchpad
```

Scratchpads are also exposed to assistants through the `scratch_pad` platform tool.

The model-facing runtime operations are:

```text
read_scratchpad
update_scratchpad
append_scratchpad
```

These two interfaces serve different purposes:

```text
ScratchpadsClient
    → application-facing resource API

scratch_pad platform tool
    → model-facing runtime API
```

---

## Deep Research

Deep Research uses Project David's delegated-worker orchestration.

A supervisor can delegate research tasks to ephemeral workers, while shared Scratchpad state provides coordination between the supervisor and workers.

The public client consumes the parent run stream.

Worker events that form part of the public stream contract are relayed back through the parent run.

These include:

```text
ScratchpadEvent
WebStatusEvent
ContentEvent
ReasoningEvent
ResearchStatusEvent
```

Raw worker tool-call mechanics remain internal to the orchestration runtime.

---

## Web Search

The `web_search` platform tool provides web research operations to assistants.

The runtime can expose operations including:

```text
perform_web_search
read_web_page
search_web_page
scroll_web_page
```

Web tool lifecycle activity is streamed as `WebStatusEvent`.

For example:

```text
running
success
warning
error
```

See the platform-tool documentation for the detailed web-search contract.

---

## Code Interpreter

The `code_interpreter` platform tool provides a Python execution environment that assistants can use for analysis and file generation.

Attach it to an assistant with:

```python
assistant = client.assistants.create_assistant(
    name="analysis_assistant",
    model="gpt-oss-120b",
    instructions="Use Python when useful.",
    tools=[
        {"type": "code_interpreter"},
    ],
)
```

Code execution can emit stream events for candidate code, execution output, and generated files.

See the [Code Interpreter documentation](https://docs.projectdavid.co.uk/docs/sdk-code-interpreter) for the streaming contract.

---

## Files

The SDK includes clients for working with files managed by the Project David platform.

Files can be used by platform components such as file search, code execution, and other tools that operate on uploaded or generated content.

See the [Files documentation](https://docs.projectdavid.co.uk/docs/10_sdk-files).

---

## Vector Stores

Vector stores provide indexed document storage for retrieval workflows.

The SDK exposes vector-store operations independently from assistant and thread management.

See the [Vector Store documentation](https://docs.projectdavid.co.uk/docs/11_sdk-vector-store).

---

## Inference Providers

Project David separates orchestration from provider-specific inference.

The provider and model used by a run are supplied through the inference configuration.

For example:

```python
for event in stream.stream_events(
    model="hyperbolic/deepseek-ai/DeepSeek-V3-0324",
):
    print(event)
```

Supported provider integrations depend on the Project David runtime configuration.

The current provider documentation is maintained here:

[Supported inference providers](https://github.com/project-david-ai/projectdavid_docs/blob/master/src/pages/providers/providers.md)

---

## Environment Variables

| Variable | Description |
|---|---|
| `PROJECTDAVID_API_KEY` | Project David API credential used by the SDK |
| `ENTITIES_USER_ID` | Project David user identifier used by inference setup |
| `BASE_URL` | Project David API base URL |
| `PROVIDER_API_KEY` | Credential for the configured inference provider |

Example:

```env
PROJECTDAVID_API_KEY=<project_david_api_key>
ENTITIES_USER_ID=<user_id>
BASE_URL=http://localhost:80
PROVIDER_API_KEY=<provider_api_key>
```

---

## Documentation

| Topic | Link |
|---|---|
| Full Documentation | [docs.projectdavid.co.uk](https://docs.projectdavid.co.uk/docs) |
| Quick Start | [SDK Quick Start](https://docs.projectdavid.co.uk/docs/sdk-quick-start) |
| Assistants | [Assistants](https://docs.projectdavid.co.uk/docs/sdk-assistants) |
| Threads | [Threads](https://docs.projectdavid.co.uk/docs/sdk-threads) |
| Messages | [Messages](https://docs.projectdavid.co.uk/docs/sdk-messages) |
| Runs | [Runs](https://docs.projectdavid.co.uk/docs/sdk-runs) |
| Inference | [Inference](https://docs.projectdavid.co.uk/docs/sdk-inference) |
| Tools | [Tools](https://docs.projectdavid.co.uk/docs/sdk-tools) |
| Function Calls | [Function Calls](https://docs.projectdavid.co.uk/docs/12_sdk-function-calls) |
| Code Interpreter | [Code Interpreter](https://docs.projectdavid.co.uk/docs/sdk-code-interpreter) |
| Files | [Files](https://docs.projectdavid.co.uk/docs/10_sdk-files) |
| Vector Store | [Vector Store](https://docs.projectdavid.co.uk/docs/11_sdk-vector-store) |
| Stream Contract | [Stream Contract](https://docs.projectdavid.co.uk/docs/sdk-stream-contract) |
| Providers | [Providers](https://docs.projectdavid.co.uk/docs/providers) |

The source documentation is maintained in:

[projectdavid_docs](https://github.com/project-david-ai/projectdavid_docs/tree/master/src/pages/sdk)

---

## Related Repositories

| Repository | Description |
|---|---|
| [projectdavid-core](https://github.com/project-david-ai/projectdavid-core) | FastAPI API and orchestration runtime |
| [projectdavid-platform](https://github.com/project-david-ai/projectdavid-platform) | Deployment and service packaging |
| [entities-common](https://github.com/project-david-ai/entities-common) | Shared validation models and utilities |
| [projectdavid_docs](https://github.com/project-david-ai/projectdavid_docs) | Project documentation |
| [entities_cook_book](https://github.com/project-david-ai/entities_cook_book) | Example integrations and tested usage patterns |

---

## License

[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)
