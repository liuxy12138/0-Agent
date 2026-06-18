import ast
import operator
from pathlib import Path
from typing import Any, Callable


ToolFunc = Callable[[dict[str, Any], dict[str, Any]], str]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[dict[str, Any], ToolFunc]] = {}

    def register(self, schema: dict[str, Any], func: ToolFunc) -> None:
        name = schema["function"]["name"]
        self._tools[name] = (schema, func)

    def schemas(self) -> list[dict[str, Any]]:
        return [schema for schema, _ in self._tools.values()]

    def run(self, name: str, args: dict[str, Any], session: dict[str, Any]) -> str:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        return self._tools[name][1](args, session)


def build_default_tools(docs_root: str = "data/docs") -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Evaluate a safe arithmetic expression.",
                "parameters": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
        },
        calculator,
    )
    registry.register(
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Mock search over built-in interview knowledge.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
        mock_search,
    )
    registry.register(
        {
            "type": "function",
            "function": {
                "name": "read_docs",
                "description": "Read local docs by topic, such as interview or agent.",
                "parameters": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                    "required": ["topic"],
                },
            },
        },
        lambda args, session: read_docs(args, session, docs_root),
    )
    registry.register(
        {
            "type": "function",
            "function": {
                "name": "todo",
                "description": "Create, update, get, or list persistent tasks for this session.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["create", "update", "get", "list"]},
                        "task_id": {"type": "string"},
                        "title": {"type": "string"},
                        "note": {"type": "string"},
                        "status": {"type": "string", "enum": ["todo", "doing", "done"]},
                    },
                    "required": ["action"],
                },
            },
        },
        todo,
    )
    registry.register(
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "Return mock weather for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        },
        weather,
    )
    return registry


def calculator(args: dict[str, Any], session: dict[str, Any]) -> str:
    expression = str(args.get("expression", ""))
    return f"{expression} = {_safe_eval(expression)}"


def mock_search(args: dict[str, Any], session: dict[str, Any]) -> str:
    query = str(args.get("query", "")).lower()
    rows = [
        "最小 Agent 的核心是 LLM、工具注册表、状态、控制循环和日志。",
        "笔试项目建议突出：无框架 runtime、可复现 demo、session 持久化、trace 可观察。",
        "跨轮次能力可以用 todo 状态演示：第一轮创建任务，第二轮查询进度并继续更新。",
    ]
    if "glm" in query:
        rows.insert(0, "GLM API 可通过 OpenAI-compatible chat completions 风格接入。")
    return "\n".join(f"- {row}" for row in rows)


def read_docs(args: dict[str, Any], session: dict[str, Any], docs_root: str) -> str:
    topic = str(args.get("topic", "")).lower() or "interview"
    root = Path(docs_root)
    candidates = sorted(root.glob("*.md"))
    for path in candidates:
        if topic in path.stem.lower():
            return path.read_text(encoding="utf-8")[:3000]
    names = ", ".join(path.stem for path in candidates) or "none"
    return f"No doc matched topic={topic}. Available topics: {names}"


def todo(args: dict[str, Any], session: dict[str, Any]) -> str:
    action = args["action"]
    tasks = session.setdefault("tasks", {})
    if action == "create":
        task_id = f"task-{len(tasks) + 1}"
        tasks[task_id] = {
            "title": args.get("title", "Untitled task"),
            "note": args.get("note", ""),
            "status": args.get("status", "todo"),
        }
        return f"created {task_id}: {tasks[task_id]}"
    if action == "update":
        task_id = str(args.get("task_id", ""))
        if task_id not in tasks:
            raise ValueError(f"Task not found: {task_id}")
        if "status" in args:
            tasks[task_id]["status"] = args["status"]
        if "note" in args:
            tasks[task_id]["note"] = args["note"]
        return f"updated {task_id}: {tasks[task_id]}"
    if action == "get":
        task_id = str(args.get("task_id", ""))
        return f"{task_id}: {tasks.get(task_id, 'not found')}"
    if action == "list":
        if not tasks:
            return "No tasks in this session."
        return "\n".join(f"{task_id}: {task}" for task_id, task in tasks.items())
    raise ValueError(f"Unsupported todo action: {action}")


def weather(args: dict[str, Any], session: dict[str, Any]) -> str:
    city = str(args.get("city", "Unknown"))
    return f"{city}: cloudy, 24C, light wind. This is mock weather for the demo."


def _safe_eval(expression: str) -> float:
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
    }

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](visit(node.operand))
        raise ValueError("Only numeric arithmetic expressions are allowed.")

    return visit(ast.parse(expression, mode="eval"))
