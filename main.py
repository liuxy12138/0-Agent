import argparse
import os
from pathlib import Path

from agent.llm import GLMClient, MockLLMClient
from agent.memory import LongTermMemory
from agent.runtime import AgentRuntime
from agent.session import SessionStore
from agent.tools import build_default_tools


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def build_runtime(mock_llm: bool, max_steps: int) -> AgentRuntime:
    llm = MockLLMClient() if mock_llm else GLMClient()
    return AgentRuntime(
        llm=llm,
        tools=build_default_tools(),
        sessions=SessionStore(),
        memory=LongTermMemory(),
        max_steps=max_steps,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal no-framework Agent with GLM API.")
    parser.add_argument("--session", default="demo", help="Session id used for persistent conversation state.")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--mock-llm", action="store_true", help="Use deterministic local model for demo.")
    parser.add_argument("--show-trace", action="store_true", help="Print tool/LLM trace after each turn.")
    args = parser.parse_args()

    load_dotenv()
    runtime = build_runtime(mock_llm=args.mock_llm, max_steps=args.max_steps)

    print(f"Minimal Agent started. session={args.session}. Type exit to quit.")
    while True:
        user_input = input("\nYou> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        result = runtime.run(user_input, args.session)
        print(f"Agent> {result.answer}")
        if args.show_trace:
            print("Trace:")
            for item in result.trace:
                print(f"  - {item}")


if __name__ == "__main__":
    main()
