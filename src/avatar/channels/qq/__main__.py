"""QQ text interface (OneBot ordinary account by default): --smoke is offline, --run connects explicitly."""

import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import time
from .bridge import QQBridge
from .engine import AvatarEngine
from .protocol import parse_event


async def smoke(root, transport="onebot"):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qq-smoke-", dir=root) as folder:
        calls = []
        outgoing = []

        def generate(message, memory):
            calls.append(message.receipt_key)
            memory.add_message("user", message.text, message.context_key)
            return "你好，我是小海。"

        bridge = QQBridge(folder, engine=AvatarEngine(generate=generate))

        async def send(message, text):
            outgoing.append({"kind": message.kind, "receipt": message.receipt_key})

        try:
            base = {
                "t": "C2C_MESSAGE_CREATE",
                "d": {
                    "id": "offline-message",
                    "timestamp": time.time(),
                    "content": "你好",
                    "author": {"user_openid": "offline-user"},
                },
            }
            if transport == "onebot":
                from .onebot import parse_onebot
                message = parse_onebot("12345", {
                    "post_type": "message", "message_type": "private", "sub_type": "friend",
                    "self_id": 12345, "user_id": 23456, "message_id": 42,
                    "time": time.time(), "message": [{"type": "text", "data": {"text": "你好"}}]})
            else:
                message = parse_event("offline-bot", base)
            first = await bridge.handle(message, send)
            again = await bridge.handle(message, send)
            assert (
                first.status == again.status == "sent"
                and len(calls) == len(outgoing) == 1
            )
            return {
                "mode": "offline-fixture",
                "transport": transport,
                "connected_to_qq": False,
                "model_called": False,
                "unique_generations": len(calls),
                "outgoing_fixture_messages": len(outgoing),
                "duplicate_suppressed": True,
            }
        finally:
            await bridge.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--health", action="store_true", help="Read-only local OneBot/model connectivity probe")
    p.add_argument("--transport", choices=("onebot", "official"), default="onebot")
    args = p.parse_args()
    if args.health:
        if args.transport != "onebot":
            p.error("--health currently supports the OneBot transport")
        from .health import health
        result = asyncio.run(health())
        print(json.dumps(result, ensure_ascii=False))
        if not result['ready']:
            raise SystemExit(1)
    elif args.check:
        from importlib.metadata import version, PackageNotFoundError
        if args.transport == "onebot":
            from .onebot_app import Settings
        else:
            from .nonebot_app import Settings

        versions = {}
        for package in ("nonebot2", "nonebot-adapter-onebot" if args.transport == "onebot" else "nonebot-adapter-qq"):
            try:
                versions[package] = version(package)
            except PackageNotFoundError:
                versions[package] = None
        try:
            Settings.environment()
            configured = True
        except ValueError:
            configured = False
        from ...config import config
        print(
            json.dumps(
                {
                    "transport": args.transport,
                    "credentials_configured": configured,
                    "model_configured": bool(config.llm.api_key),
                    "sdk_versions": versions,
                    "connected_to_qq": False,
                    "network_called": False,
                },
                ensure_ascii=False,
            )
        )
    elif args.smoke:
        project = Path(__file__).resolve().parents[4]
        print(
            json.dumps(
                asyncio.run(smoke(project / "data/qq-tests", args.transport)), ensure_ascii=False
            )
        )
    else:
        try:
            if args.transport == "onebot":
                from .onebot_app import run
            else:
                from .nonebot_app import run

            run()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise SystemExit(
                "QQ service failed: "
                + type(exc).__name__
                + "; check local configuration and optional dependencies."
            ) from None


if __name__ == "__main__":
    main()
