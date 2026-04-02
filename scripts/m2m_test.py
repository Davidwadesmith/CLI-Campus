#!/usr/bin/env python3
"""M2M 联调测试 — 测试 LLM 能否正确调用 CLI-Campus 工具。

使用方法:
    # 设置 API Key (支持 DeepSeek / OpenAI 兼容接口)
    export OPENAI_API_KEY="your-api-key"
    export OPENAI_BASE_URL="https://api.deepseek.com"  # 可选

    # 运行测试
    python scripts/m2m_test.py "查一下明天下午去丁家桥的校车"
    python scripts/m2m_test.py "我这学期有什么课"
    python scripts/m2m_test.py "帮我查一下教务处最新通知"

依赖:
    pip install openai
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. 加载 CLI-Campus Tool Schema
# ---------------------------------------------------------------------------


def load_tools() -> list[dict]:
    """通过 campus schema export 加载 Tool Schema。"""
    project_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "cli_campus.main", "schema", "export"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    if result.returncode != 0:
        print(f"❌ 无法加载 Tool Schema: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# 2. 执行 CLI 命令
# ---------------------------------------------------------------------------


def run_campus_command(func_name: str, arguments: dict) -> str:
    """将 Function Calling 结果转换为 CLI 命令并执行。"""
    # campus_bus → bus, campus_auth_login → auth login
    cmd_parts = func_name.replace("campus_", "").split("_")
    cmd = [sys.executable, "-m", "cli_campus.main", "--json"]

    # 处理子命令组 (如 auth_login → auth login)
    if len(cmd_parts) >= 2 and cmd_parts[0] in ("auth",):
        cmd.extend(cmd_parts)
    else:
        cmd.append("-".join(cmd_parts))

    # 添加参数
    for key, value in arguments.items():
        param_name = key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                cmd.append(f"--{param_name}")
        else:
            cmd.extend([f"--{param_name}", str(value)])

    project_root = Path(__file__).resolve().parent.parent
    print(f"  🔧 执行: {' '.join(cmd[2:])}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(project_root),
    )
    if result.stdout:
        return result.stdout.strip()
    stderr = result.stderr.strip()[:200] if result.stderr else ""
    return f"(exit={result.returncode}) {stderr}"


# ---------------------------------------------------------------------------
# 3. LLM 交互
# ---------------------------------------------------------------------------


def main() -> None:
    # 检查依赖
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 请安装 openai 库: pip install openai")
        sys.exit(1)

    # 获取用户输入
    if len(sys.argv) < 2:
        user_message = "查一下校车时刻表"
        print(f"  (默认查询: {user_message})")
    else:
        user_message = " ".join(sys.argv[1:])

    # 检查 API Key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ 请设置环境变量 OPENAI_API_KEY")
        print("  export OPENAI_API_KEY='your-api-key'")
        print("  export OPENAI_BASE_URL='https://api.deepseek.com'  # 可选")
        sys.exit(1)

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("OPENAI_MODEL", "deepseek-chat")

    print(f"\n📡 API: {base_url} / {model}")
    print(f"💬 用户: {user_message}\n")

    # 加载 Tool Schema
    tools = load_tools()
    print(f"🔑 已加载 {len(tools)} 个工具 Schema\n")

    # 发送请求
    client = OpenAI(api_key=api_key, base_url=base_url)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你是东南大学的校园助手。"
                "使用提供的工具回答问题。回答简洁明了。",
            },
            {"role": "user", "content": user_message},
        ],
        tools=tools,
        tool_choice="auto",
    )

    message = response.choices[0].message

    # 处理工具调用
    if message.tool_calls:
        tool_results = []
        for tc in message.tool_calls:
            func = tc.function
            args = json.loads(func.arguments) if func.arguments else {}
            print(f"🤖 LLM 调用: {func.name}({json.dumps(args, ensure_ascii=False)})")

            result = run_campus_command(func.name, args)
            tool_results.append({
                "tool_call_id": tc.id,
                "role": "tool",
                "content": result,
            })
            print(f"  📦 结果: {result[:200]}{'...' if len(result) > 200 else ''}\n")

        # 将结果发回 LLM 获取最终回答
        follow_up = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是东南大学的校园助手。"
                    "使用提供的工具回答问题。回答简洁明了。",
                },
                {"role": "user", "content": user_message},
                message,
                *tool_results,
            ],
        )
        final = follow_up.choices[0].message.content
        print(f"🎓 最终回答:\n{final}")
    else:
        print(f"🎓 LLM 直接回答:\n{message.content}")


if __name__ == "__main__":
    main()
