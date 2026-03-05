# API Features Overview

Claude's API is organized into five areas:

1. **Files and assets** — Manage documents and data you provide to Claude
2. **Context management** — Keep long-running sessions efficient
3. **Tool infrastructure** — Discovery and orchestration at scale
4. **Tools** — Let Claude take actions on the web or in your environment
5. **Model capabilities** — Control how Claude reasons and formats responses

## Model Capabilities

| Feature | Description |
|---------|-------------|
| [1M token context window](https://docs.anthropic.com/docs/en/build-with-claude/context-windows#1m-token-context-window) | Process larger documents, longer conversations, extensive codebases |
| [Adaptive thinking](https://docs.anthropic.com/docs/en/build-with-claude/adaptive-thinking) | Claude dynamically decides when and how much to think |
| [Batch processing](https://docs.anthropic.com/docs/en/build-with-claude/batch-processing) | Async processing, 50% cost reduction |
| [Citations](https://docs.anthropic.com/docs/en/build-with-claude/citations) | Ground responses in source documents with references |
| [Data residency](https://docs.anthropic.com/docs/en/build-with-claude/data-residency) | Control where inference runs via `inference_geo` |
| [Effort](https://docs.anthropic.com/docs/en/build-with-claude/effort) | Trade off thoroughness vs token efficiency |
| [Extended thinking](https://docs.anthropic.com/docs/en/build-with-claude/extended-thinking) | Step-by-step reasoning with transparency |
| [PDF support](https://docs.anthropic.com/docs/en/build-with-claude/pdf-support) | Process text and visual content from PDFs |
| [Structured outputs](https://docs.anthropic.com/docs/en/build-with-claude/structured-outputs) | Guaranteed schema conformance (JSON, strict tool use) |

## Tools

### Server-side (run by platform)

| Feature | Description |
|---------|-------------|
| [Code execution](https://docs.anthropic.com/docs/en/agents-and-tools/tool-use/code-execution-tool) | Run code in sandbox for data analysis, calculations |
| [Memory](https://docs.anthropic.com/docs/en/agents-and-tools/tool-use/memory-tool) | Store and retrieve info across conversations |
| [Web fetch](https://docs.anthropic.com/docs/en/agents-and-tools/tool-use/web-fetch-tool) | Retrieve content from web pages and PDFs |
| [Web search](https://docs.anthropic.com/docs/en/agents-and-tools/tool-use/web-search-tool) | Augment with current web data |

### Client-side (you implement)

| Feature | Description |
|---------|-------------|
| [Bash](https://docs.anthropic.com/docs/en/agents-and-tools/tool-use/bash-tool) | Execute bash commands |
| [Computer use](https://docs.anthropic.com/docs/en/agents-and-tools/tool-use/computer-use-tool) | Screenshots, mouse/keyboard control |
| [Text editor](https://docs.anthropic.com/docs/en/agents-and-tools/tool-use/text-editor-tool) | Create and edit text files |

## Tool Infrastructure

| Feature | Description |
|---------|-------------|
| [Agent Skills](https://docs.anthropic.com/docs/en/agents-and-tools/agent-skills/overview) | Pre-built (PowerPoint, Excel, Word, PDF) or custom skills |
| [Fine-grained tool streaming](https://docs.anthropic.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming) | Stream tool params without buffering |
| [MCP connector](https://docs.anthropic.com/docs/en/agents-and-tools/mcp-connector) | Connect to MCP servers from Messages API |
| [Tool search](https://docs.anthropic.com/docs/en/agents-and-tools/tool-use/tool-search-tool) | Scale to thousands of tools with on-demand discovery |

## Context Management

| Feature | Description |
|---------|-------------|
| [Compaction](https://docs.anthropic.com/docs/en/build-with-claude/compaction) | Server-side summarization for long conversations |
| [Context editing](https://docs.anthropic.com/docs/en/build-with-claude/context-editing) | Auto-manage context, clear tool results |
| [Automatic prompt caching](https://docs.anthropic.com/docs/en/build-with-claude/prompt-caching#automatic-caching) | Single API parameter for caching |
| [Prompt caching (5m/1hr)](https://docs.anthropic.com/docs/en/build-with-claude/prompt-caching) | Reduce costs and latency |
| [Token counting](https://docs.anthropic.com/docs/en/api/messages-count-tokens) | Count tokens before sending |

## Files and Assets

| Feature | Description |
|---------|-------------|
| [Files API](https://docs.anthropic.com/docs/en/build-with-claude/files) | Upload and manage files for use across requests. Supports PDFs, images, text. |
