import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMMessage:
    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class GLMClient:
    """Tiny OpenAI-compatible client for GLM chat completions."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GLM_API_KEY", "")
        self.base_url = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.model = os.getenv("GLM_MODEL", "glm-4-flash")

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMMessage:
        if not self.api_key:
            raise RuntimeError("GLM_API_KEY is not set. Copy .env.example or set the environment variable.")

        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GLM API HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GLM API request failed: {exc.reason}") from exc

        message = data["choices"][0]["message"]
        return LLMMessage(
            role=message.get("role", "assistant"),
            content=message.get("content"),
            tool_calls=message.get("tool_calls"),
        )


class MockLLMClient:
    """Deterministic demo model for local verification without spending API quota."""

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMMessage:
        last = next((m for m in reversed(messages) if m["role"] in {"user", "tool"}), {})
        text = str(last.get("content") or "").lower()

        if last.get("role") == "tool":
            if "created" in text or "updated" in text or "tasks" in text:
                return LLMMessage(role="assistant", content="我已经记录并更新了任务状态。后续你问进度时，我会基于这个 session 继续处理。")
            return LLMMessage(role="assistant", content=f"工具结果已读取：{last.get('content')}")

        if "进度" in text or "progress" in text:
            return self._tool_call("todo", {"action": "list"})
        if "计算" in text or any(op in text for op in ["+", "-", "*", "/"]):
            return self._tool_call("calculator", {"expression": "12 * 8 + 4"})
        if "天气" in text:
            return self._tool_call("weather", {"city": "Beijing"})
        if "文档" in text or "面试" in text:
            return self._tool_call("read_docs", {"topic": "interview"})
        if "搜索" in text or "search" in text:
            return self._tool_call("search", {"query": text[:80]})
        if "任务" in text or "todo" in text or "准备" in text:
            return self._tool_call("todo", {"action": "create", "title": "准备 agent 笔试 demo", "note": "实现最小 runtime、工具调用、session 记忆和 trace。"})
        return LLMMessage(role="assistant", content="这是一个无框架最小 Agent。你可以让我创建任务、查进度、计算、搜索 mock、读取文档或查询天气。")

    def _tool_call(self, name: str, arguments: dict[str, Any]) -> LLMMessage:
        return LLMMessage(
            role="assistant",
            content=None,
            tool_calls=[
                {
                    "id": f"mock_{name}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                }
            ],
        )
