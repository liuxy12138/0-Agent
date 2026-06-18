import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent.llm import LLMMessage
from agent.memory import LongTermMemory
from agent.session import SessionStore
from agent.tools import ToolRegistry


SYSTEM_PROMPT = """你是一个实习准备助理 Agent。
你可以直接回答，也可以调用工具。需要工具时只调用必要工具。
如果用户问任务、进度、继续、状态，请优先查看 todo，因为 session 中可能已有任务。
回答要简洁，但要说明你基于哪些工具结果或已有状态。"""


@dataclass
class AgentResult:
    answer: str
    session_id: str
    steps: int
    trace: list[dict[str, Any]]


class AgentRuntime:
    """Hand-written ReAct-style runtime: LLM -> tool calls -> tool results -> final answer."""

    def __init__(
        self,
        llm: Any,
        tools: ToolRegistry,
        sessions: SessionStore,
        memory: LongTermMemory,
        max_steps: int = 6,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.sessions = sessions
        self.memory = memory
        self.max_steps = max_steps

    def run(self, user_input: str, session_id: str) -> AgentResult:
        session = self.sessions.load(session_id)
        session["messages"].append({"role": "user", "content": user_input})
        self.memory.add(session_id, "user", user_input)
        turn_trace: list[dict[str, Any]] = []

        for step in range(1, self.max_steps + 1):
            messages = self._build_messages(session, user_input)
            try:
                response: LLMMessage = self.llm.chat(messages, self.tools.schemas())
            except Exception as exc:
                answer = f"LLM 调用失败：{exc}"
                session["messages"].append({"role": "assistant", "content": answer})
                self._record_trace(session, turn_trace, "llm_error", {"step": step, "error": str(exc)})
                self.sessions.save(session)
                return AgentResult(answer=answer, session_id=session_id, steps=step, trace=turn_trace)

            self._record_trace(
                session,
                turn_trace,
                "llm_response",
                {"step": step, "content": response.content, "tool_calls": response.tool_calls or []},
            )

            if not response.tool_calls:
                answer = response.content or ""
                session["messages"].append({"role": "assistant", "content": answer})
                self.memory.add(session_id, "assistant", answer)
                self.sessions.save(session)
                return AgentResult(answer=answer, session_id=session_id, steps=step, trace=turn_trace)

            assistant_message = {"role": "assistant", "content": response.content, "tool_calls": response.tool_calls}
            session["messages"].append(assistant_message)

            for call in response.tool_calls:
                tool_id = call.get("id", "")
                function = call.get("function", {})
                name = function.get("name")
                try:
                    args = json.loads(function.get("arguments") or "{}")
                    result = self.tools.run(name, args, session)
                    self._record_trace(
                        session,
                        turn_trace,
                        "tool_result",
                        {"step": step, "tool": name, "args": args, "result": result},
                    )
                except Exception as exc:
                    result = f"Tool error in {name}: {exc}"
                    self._record_trace(
                        session,
                        turn_trace,
                        "tool_error",
                        {"step": step, "tool": name, "error": str(exc)},
                    )

                session["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": name,
                        "content": result,
                    }
                )
                self.sessions.save(session)

        answer = f"达到最大步数限制 max_steps={self.max_steps}，已停止。你可以继续追问，我会基于当前 session 状态接着处理。"
        session["messages"].append({"role": "assistant", "content": answer})
        self.sessions.save(session)
        return AgentResult(answer=answer, session_id=session_id, steps=self.max_steps, trace=turn_trace)

    def _build_messages(self, session: dict[str, Any], user_input: str) -> list[dict[str, Any]]:
        memories = self.memory.search(user_input, session_id=session["session_id"], top_k=3)
        memory_text = "\n".join(f"- {item['role']}: {item['text']}" for item in memories)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if memory_text:
            messages.append({"role": "system", "content": f"相关长期记忆：\n{memory_text}"})
        messages.extend(session["messages"][-20:])
        return messages

    def _record_trace(
        self,
        session: dict[str, Any],
        turn_trace: list[dict[str, Any]],
        event: str,
        payload: dict[str, Any],
    ) -> None:
        item = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
        session.setdefault("trace", []).append(item)
        turn_trace.append(item)
