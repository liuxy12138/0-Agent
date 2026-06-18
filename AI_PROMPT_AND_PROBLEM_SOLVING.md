# AI Prompt 与问题解决记录

## 1. 背景与目标

本项目要求从 0 实现一个最小可用 Agent，不使用 LangChain、LangGraph、OpenHands 等现成 Agent 框架完成核心主流程。

Agent 需要具备以下能力：

- 支持多轮对话和 session 维护
- 支持真实 LLM API，本项目使用 GLM API
- 支持“直接回答 / 调用工具”的判断
- 支持工具执行、工具结果回填和继续推理
- 至少提供 3 个工具
- 支持最大步数限制
- 支持基本异常处理
- 支持工具调用 trace 或执行日志
- 支持跨轮次继续执行
- 支持简单短期记忆和长期记忆

AI 在本项目中主要用于辅助需求拆解、架构设计、代码实现建议、问题排查和文档组织。核心代码经过人工理解、取舍、修改和验证。

## 2. Prompt 使用记录

以下记录不是完整聊天内容，而是开发过程中关键 Prompt 的整理摘要。

| 阶段 | Prompt 摘要 | 目的 | 产出 |
|---|---|---|---|
| Agent 原理理解 | 如果不使用 LangGraph、LangChain、OpenHands 等框架，一个 Agent 是否还可以实现？这些框架主要提供什么？ | 理解 Agent 的核心组成 | 明确 Agent 本质是 LLM、状态、工具和控制循环 |
| 任务需求拆解 | 从 0 实现一个最小可用 Agent，不使用框架，支持多轮对话、session、工具、trace、memory 和 GLM API | 拆解笔试需求 | 明确必须实现 runtime、tool registry、session store、memory、LLM client |
| 场景选择 | 这是实习面试前的笔试，不确定什么场景比较合适 | 选择适合展示的业务场景 | 确定“实习准备助理”作为 demo 场景 |
| 系统实现 | 根据需求实现一个最小可用 Agent 项目 | 生成可运行项目 | 创建 `agent/runtime.py`、`tools.py`、`session.py`、`memory.py`、`llm.py` 和 CLI 入口 |
| 文档完善 | README 需要有运行方式、系统设计、memory 的召回时机和放置方式说明 | 完善提交文档 | 补充 README 中的运行方式、系统设计、memory 写入和召回说明 |
| 问题记录 | 提交时需要有 AI Prompt 与问题解决记录，应该怎么做 | 形成提交材料 | 生成本文档，记录关键 prompt、问题和解决过程 |

## 3. 关键设计决策

### 3.1 为什么选择“实习准备助理”作为场景

最初的问题是：Agent 场景还没有确定，而笔试项目需要既简单又能体现核心能力。

最终选择“实习准备助理”，原因是：

- 它天然需要任务状态管理，适合展示跨轮次继续执行。
- 它可以合理使用 `todo`、`read_docs`、`search`、`calculator` 等工具。
- 它不需要复杂外部服务，方便评审本地运行。
- 它能把 Agent 的主流程展示清楚，而不是只做普通聊天机器人。

例如：

```text
第一轮：帮我创建一个准备 agent 笔试的任务
第二轮：现在进度如何？
```

第二轮中，Agent 需要基于第一轮保存在 session 中的任务继续回答，而不是把用户问题当成全新的独立请求。

### 3.2 为什么不使用 Agent 框架

本项目的目标是展示 Agent 的最小核心机制，因此没有使用现成 Agent 框架完成主流程。

以下能力都由项目代码直接实现：

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

这样做可以更清楚地展示对 Agent runtime 的理解。

### 3.3 为什么保留 mock LLM

项目默认支持真实 GLM API，但同时保留 `MockLLMClient`。

原因是：

- 评审本地可能没有 GLM API key。
- mock 模式可以快速验证主流程是否跑通。
- mock 模式不会影响真实 GLM 接入，因为两者实现了相同的 `chat()` 调用接口。

运行方式：

```bash
python main.py --session interview-demo --mock-llm --show-trace
```

## 4. 问题解决记录

### 问题 1：不用 Agent 框架时，主循环如何设计？

**挑战：**

需要实现一个 Agent 基本循环：接收用户输入，判断是直接回答还是调用工具，执行工具，读取工具结果，继续下一步，直到最终回答。

**分析：**

Agent 的核心不是框架本身，而是一个控制循环：

```text
LLM response
  -> 如果有 tool_calls，执行工具
  -> 将 tool result 放回 messages
  -> 再次调用 LLM
  -> 如果没有 tool_calls，返回最终答案
```

**解决方案：**

在 `agent/runtime.py` 中实现 `AgentRuntime.run()`：

- 每轮最多执行 `max_steps` 步。
- 每一步调用 LLM。
- 如果 LLM 返回 `tool_calls`，解析参数并执行工具。
- 工具结果以 `tool` message 的形式写回 session。
- 如果 LLM 没有返回工具调用，则保存最终回答并结束。

**结果：**

实现了一个最小 ReAct-style runtime，并且没有依赖现成 Agent 框架。

### 问题 2：如何支持跨轮次继续执行？

**挑战：**

笔试要求 Agent 不能把每一轮都当成全新问题。第一轮创建任务后，第二轮用户追问进度，Agent 需要基于已有状态继续处理。

**分析：**

需要区分两类状态：

- 当前对话上下文：最近的 messages。
- 业务状态：例如当前 session 下的 todo tasks。

如果只保存 messages，模型可能能理解上下文，但任务状态不够结构化。为了更稳定地演示跨轮次能力，需要把任务单独放在 session 的 `tasks` 字段中。

**解决方案：**

在 `SessionStore` 中使用 JSON 文件持久化 session：

```text
data/sessions/{session_id}.json
```

session 中保存：

```text
messages
tasks
trace
created_at
updated_at
```

`todo` 工具会读写 `session["tasks"]`。第一轮创建任务时写入 `tasks`，第二轮问进度时调用 `todo list` 查询已有任务。

**结果：**

mock 测试中可以完成：

```text
第一轮：帮我创建一个准备 agent 笔试的任务
第二轮：现在进度如何？
```

第二轮能读取第一轮创建的 `task-1`。

### 问题 3：memory 应该什么时候写入，什么时候召回？

**挑战：**

项目需要支持短期记忆和长期记忆，但如果把所有内容都塞进 memory，会造成信息冗余和召回噪声。

**分析：**

短期记忆适合保存完整对话和工具结果，长期记忆适合保存更有复用价值的信息。

因此做了如下划分：

- 短期记忆：session messages、tasks、trace。
- 长期记忆：用户输入和 assistant 最终回答。

工具中间结果不默认写入长期记忆，因为它们已经保存在 session messages 和 trace 中。

**解决方案：**

长期记忆写入时机：

```text
用户输入进入 runtime 后，写入 memory
LLM 给出最终回答后，写入 memory
```

长期记忆召回时机：

```text
每一次调用 LLM 前，在 _build_messages() 中根据当前 user_input 召回 top_k=3 条相关记忆
```

召回后的 memory 放在 prompt 中：

```text
system prompt
相关长期记忆
recent session messages
```

**结果：**

Agent 同时具备：

- session 级短期上下文
- 可持久化的长期向量记忆
- 每次 LLM 调用前的 memory retrieval

### 问题 4：FAISS 接入时报错 `list object has no attribute shape`

**现象：**

本地 mock 测试时，环境中已经安装了 FAISS，但调用 `index.add()` 报错：

```text
AttributeError: 'list' object has no attribute 'shape'
```

**原因：**

FAISS Python API 需要传入 `float32` 类型的 numpy array，形状应为 `[n, dim]`。最初传入的是 Python list。

**解决方案：**

在 `LongTermMemory` 中增加 `_as_faiss_matrix()` 方法：

```python
def _as_faiss_matrix(self, rows: list[list[float]]) -> Any:
    import numpy as np
    return np.array(rows, dtype="float32")
```

写入和召回时都通过这个方法转换：

```python
self.index.add(self._as_faiss_matrix([item["embedding"]]))
```

**结果：**

FAISS 分支可以正常运行，mock demo 可以完成任务创建、进度查询和计算工具调用。

### 问题 5：hashing vector 是否稳定？

**挑战：**

长期记忆使用轻量 hashing vector。如果直接使用 Python 内置 `hash()`，不同进程中的 hash 结果可能不同。

**分析：**

Python 默认 hash 有随机化机制。对于需要持久化到磁盘的向量记忆，如果使用不稳定 hash，重启进程后新写入的向量和旧向量可能不在同一空间。

**解决方案：**

改用 `hashlib.sha256` 生成稳定 hash：

```python
idx = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.dim
```

**结果：**

长期记忆的向量空间在不同进程中保持一致，更适合持久化存储。

### 问题 6：如何记录工具调用过程，便于评审理解？

**挑战：**

Agent 的执行过程如果不可见，评审很难判断工具是否真的被调用，或者模型是否只是在编造结果。

**分析：**

需要记录每一步 LLM 响应、工具调用、工具参数、工具结果和异常。

**解决方案：**

在 runtime 中实现 `_record_trace()`，每次记录 event：

- `llm_response`
- `tool_result`
- `tool_error`
- `llm_error`

trace 同时返回给 CLI，并保存到 session 文件。

运行时使用：

```bash
python main.py --session interview-demo --mock-llm --show-trace
```

**结果：**

每轮对话后可以看到完整执行轨迹，便于调试和展示。

## 5. 验证记录

### 5.1 语法检查

执行：

```bash
python -m py_compile agent\llm.py agent\memory.py agent\runtime.py agent\session.py agent\tools.py main.py
```

结果：通过。

### 5.2 mock 多轮测试

执行：

```bash
python main.py --session interview-demo --mock-llm --show-trace
```

测试输入：

```text
帮我创建一个准备 agent 笔试的任务
现在进度如何？
计算一下 12 * 8 + 4
```

验证点：

- 第一轮创建 `task-1`。
- 第二轮可以读取 session 中已有任务。
- 第三轮调用 `calculator` 工具。
- trace 中包含 `llm_response`、`tool_result`、`llm_response`。

## 6. AI 辅助与人工决策边界

AI 辅助完成了：

- 需求拆解
- 架构建议
- 代码初稿生成
- README 结构整理
- 问题排查建议
- 本问题解决记录整理

人工确认和取舍包括：

- 选择“实习准备助理”作为 demo 场景。
- 不使用 Agent 框架完成主流程。
- 使用 JSON 文件保存 session，降低运行复杂度。
- 保留 mock LLM，方便无 API key 情况下验证。
- 长期记忆不写入所有工具中间结果，避免 memory 膨胀。
- trace 作为主要可观察性手段，方便笔试评审。

## 7. 后续改进方向

如果继续完善，可以考虑：

- 使用真实 embedding model 替换 hashing vector。
- 增加单元测试和端到端测试。
- 增加工具权限控制，避免危险工具直接执行。
- 支持跨 session 的长期记忆召回。
- 增加 Web UI 或 HTTP API。
- 增加更完整的任务规划和任务状态流转。
- 增加 checkpoint，使长任务可以中断后恢复。
