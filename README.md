# Minimal No-Framework Agent

这是一个从 0 实现的最小可用 Agent，用于实习笔试展示。项目不使用 LangChain、LangGraph、OpenHands 等现成 Agent 框架来完成核心主流程，而是自己实现 LLM 调用、工具路由、循环控制、session 维护、memory 召回和 trace 日志。

## 1. 项目场景

本项目选择的场景是“实习准备助理”。这个 Agent 可以帮助用户维护笔试准备任务，并在多轮对话中继续跟进已有任务状态。

它支持：

- 创建和维护准备任务
- 跨轮次查询任务进度
- 计算表达式
- mock 搜索 Agent 笔试资料
- 读取本地文档
- 查询 mock 天气

这个场景适合笔试展示，因为它能自然体现 Agent 的核心能力：工具调用、状态维护、短期记忆、长期记忆、跨轮次继续执行和执行 trace。

## 2. 运行方式

### 2.1 安装依赖

```bash
cd minimal_agent
pip install -r requirements.txt
```

`requirements.txt` 中包含 `faiss-cpu`。如果本地暂时没有安装 FAISS，项目仍然可以运行，`LongTermMemory` 会自动退化为纯 Python cosine search。

### 2.2 配置 GLM API

复制 `.env.example` 为 `.env`：

```bash
copy .env.example .env
```

然后填写：

```text
GLM_API_KEY=your_glm_api_key
GLM_MODEL=glm-4-flash
GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
```

项目使用 GLM 的 OpenAI-compatible chat completions 接口，代码位置在 `agent/llm.py`。

### 2.3 使用真实 GLM 运行

```bash
python main.py --session interview-demo --show-trace
```

参数说明：

- `--session interview-demo`：指定 session id，同一个 session 会复用历史对话、任务和 trace。
- `--show-trace`：每轮输出 LLM 响应、工具调用和工具结果。
- `--max-steps 6`：可选，限制单轮 Agent 最多循环步数，默认是 6。

### 2.4 使用 mock LLM 本地演示

如果没有 API key，或者想快速验证主流程，可以运行：

```bash
python main.py --session interview-demo --mock-llm --show-trace
```

推荐演示输入：

```text
帮我创建一个准备 agent 笔试的任务
现在进度如何？
计算一下 12 * 8 + 4
搜索一下最小 agent 应该展示哪些能力
读取面试文档
```

第二轮“现在进度如何？”会读取上一轮保存在 session 中的任务，而不是把这一轮当成全新问题。

## 3. 系统设计

### 3.1 整体流程

```text
用户输入
  -> 加载 session
  -> 写入当前用户消息
  -> 写入长期记忆
  -> 根据当前输入召回相关长期记忆
  -> 构造 messages
  -> 调用 LLM
      -> 如果 LLM 直接回答：保存回答，结束本轮
      -> 如果 LLM 请求工具：执行工具，写入 tool result，继续循环
  -> 达到最终回答或 max_steps 上限
  -> 保存 session
```

### 3.2 核心模块

- `main.py`：CLI 入口，负责读取参数、加载 `.env`、创建 runtime。
- `agent/runtime.py`：手写 Agent runtime，包含主循环、最大步数限制、工具调用、异常处理、trace 记录。
- `agent/llm.py`：GLM API client 和 mock LLM client。
- `agent/tools.py`：工具注册表和工具实现。
- `agent/session.py`：session 持久化，把 messages、tasks、trace 存到 JSON。
- `agent/memory.py`：长期记忆，负责文本向量化、写入、召回。
- `data/docs/interview.md`：本地文档，供 `read_docs` 工具读取。

### 3.3 Agent 主循环

核心循环在 `AgentRuntime.run()` 中：

```text
for step in range(1, max_steps + 1):
    messages = build_messages(session, user_input)
    response = llm.chat(messages, tools)

    if response has no tool_calls:
        save assistant answer
        return final answer

    for each tool_call:
        parse arguments
        run tool
        append tool result to messages/session
        continue next LLM step
```

这个循环没有依赖现成 Agent 框架。工具 schema、工具路由、工具执行、结果回填和循环终止都由项目代码自己控制。

## 4. 工具设计

工具通过 `ToolRegistry` 注册，每个工具包含：

- tool schema：提供给 LLM，用于说明工具名称、描述和参数。
- tool function：本地 Python 函数，负责执行实际逻辑。

当前内置工具：

- `calculator`：安全计算四则表达式。
- `search`：mock 搜索，返回内置的 Agent 笔试建议。
- `read_docs`：读取 `data/docs` 下的本地文档。
- `todo`：创建、更新、查询、列出 session 内任务。
- `weather`：mock 天气查询。

跨轮次继续执行主要依赖 `todo` 工具和 session 状态。例如第一轮创建任务后，任务会保存到当前 session 的 `tasks` 字段；第二轮用户问“进度如何”，Agent 可以再次调用 `todo list` 读取已有任务。

## 5. Session 和 Memory 设计

### 5.1 短期记忆：Session

短期记忆放在 session 文件中，默认路径：

```text
data/sessions/{session_id}.json
```

session 中保存：

- `messages`：最近多轮对话和 tool result。
- `tasks`：当前 session 下的任务状态。
- `trace`：LLM 响应、工具调用、工具结果和异常日志。
- `created_at` / `updated_at`：session 时间戳。

在构造 prompt 时，runtime 会把 `session["messages"][-20:]` 放入 messages，作为短期上下文。这样 Agent 可以看到最近的用户输入、assistant 响应和工具结果。

### 5.2 长期记忆：Vector Memory

长期记忆由 `LongTermMemory` 实现，默认路径：

```text
data/memory/memory.json
```

每条长期记忆包含：

```text
session_id
role
text
embedding
```

当前 demo 使用轻量 embedding 方案：对文本分词后做 hashing vector，并归一化。这样不需要额外 embedding API，也能展示完整的向量记忆流程。

如果环境中安装了 FAISS：

- 初始化时会创建 `faiss.IndexFlatIP`
- 新增记忆时同步 add 到 FAISS index
- 召回时优先走 FAISS inner product search

如果没有 FAISS：

- 自动使用纯 Python cosine similarity
- 项目仍可运行

### 5.3 Memory 的写入时机

长期记忆的写入发生在两个地方：

1. 用户输入进入 runtime 后，立即写入长期记忆：

```text
self.memory.add(session_id, "user", user_input)
```

2. LLM 给出最终回答后，写入 assistant 回答：

```text
self.memory.add(session_id, "assistant", answer)
```

工具中间结果不会默认写入长期记忆。原因是工具结果通常已经保存在 session messages 和 trace 中；长期记忆只保留对后续对话更有价值的用户意图和最终回答，避免 memory 过快膨胀。

### 5.4 Memory 的召回时机

长期记忆的召回发生在每一次调用 LLM 之前，也就是 `_build_messages()` 中：

```text
memories = self.memory.search(user_input, session_id=session["session_id"], top_k=3)
```

也就是说，每个 Agent step 都会根据当前用户输入召回相关记忆，再把召回结果放进 prompt。

这样设计的原因是：

- 第一轮可以写入用户意图。
- 后续轮次可以根据新问题召回历史相关内容。
- 工具执行后下一次 LLM 调用仍然能看到相同的长期记忆和最新 tool result。

### 5.5 Memory 的放置方式

召回出的 memory 被放在 system message 中，位置在主 system prompt 之后、历史 messages 之前：

```text
[
  {"role": "system", "content": SYSTEM_PROMPT},
  {"role": "system", "content": "相关长期记忆：..."},
  ...recent session messages
]
```

这种放置方式的考虑：

- 主 system prompt 保持最高优先级，定义 Agent 角色和工具使用原则。
- 相关长期记忆作为补充背景，放在历史消息之前，方便模型提前获得上下文。
- 最近 20 条 session messages 仍然保留，保证短期对话连续性。

## 6. Trace 和异常处理

每一轮执行都会记录 trace，保存在 session 的 `trace` 字段中。

trace event 包括：

- `llm_response`：LLM 返回内容和 tool calls。
- `tool_result`：工具名称、参数和执行结果。
- `tool_error`：工具执行异常。
- `llm_error`：LLM API 调用异常。

如果工具报错，runtime 不会直接崩溃，而是把错误作为 tool result 写回对话，让 LLM 有机会解释或修正。  
如果 LLM API 报错，runtime 会返回明确错误信息并保存 session。

### 6.1 异常处理覆盖范围

本项目实现的是最小可用级别的基本异常处理，主要覆盖以下情况：

| 异常类型 | 触发场景 | 处理方式 | 代码位置 |
|---|---|---|---|
| LLM 调用异常 | GLM API key 未配置、网络失败、接口异常 | 捕获异常，返回可读错误，记录 `llm_error`，保存 session | `agent/runtime.py` |
| HTTP 请求异常 | GLM 接口返回 HTTP error 或 URL error | 包装成 `RuntimeError`，携带 HTTP 状态码或网络错误原因 | `agent/llm.py` |
| 工具参数异常 | LLM 返回的 tool arguments 不是合法 JSON | 捕获异常，写入 `tool_error`，把错误作为 tool result 返回 | `agent/runtime.py` |
| 未知工具异常 | LLM 请求了未注册工具 | `ToolRegistry` 抛出 `ValueError`，runtime 捕获并记录 | `agent/tools.py` |
| 工具内部异常 | calculator 表达式非法、todo 查询不存在任务等 | 捕获异常，记录 `tool_error`，不中断整个 Agent 进程 | `agent/runtime.py` |
| 无限循环风险 | LLM 一直请求工具但不给最终答案 | 使用 `max_steps` 限制单轮最大步数，超限后返回提示 | `agent/runtime.py` |

异常处理的目标不是隐藏错误，而是让 Agent 在出错时保持可观察、可恢复：

- 错误会进入 trace，便于调试。
- session 会被保存，便于下一轮继续。
- 工具错误会作为 tool result 回填给 LLM，让模型有机会修正参数或解释失败。
- LLM API 错误会直接返回给用户，避免程序无提示退出。

## 7. 为什么这不是套框架

本项目没有使用现成 Agent 框架完成主流程。以下能力都在项目内直接实现：

- LLM API 调用
- tool schema 定义
- tool registry
- tool call 参数解析
- tool routing
- tool result 回填
- Agent 循环控制
- 最大步数限制
- session 持久化
- memory 写入和召回
- trace 日志
- 基本异常处理

框架可以进一步提供可视化编排、checkpoint、复杂 DAG、多 Agent 协作等能力，但这个项目的目标是展示一个 Agent 的最小核心机制。
