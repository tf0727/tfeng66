"""Run the consultant agent from a terminal."""

from agent.runtime import ConsultantLoop as AgentLoop


def main() -> None:
    print("编程培训咨询 Agent（输入 quit 退出）")
    try:
        loop = AgentLoop()
    except RuntimeError as exc:
        print(f"配置错误：{exc}")
        return
    while True:
        try:
            user_input = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return
        if user_input.lower() in {"quit", "exit", "q"}:
            print("已退出。")
            return
        if not user_input:
            continue
        print("Agent：", end="", flush=True)
        try:
            for chunk in loop.run(user_input):
                print(chunk, end="", flush=True)
            print()
        except Exception as exc:  # CLI should fail gracefully in the demo.
            print(f"\n请求失败：{exc}")


if __name__ == "__main__":
    main()
