"""Installed and source-tree application entry, with an offline readiness report."""
import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys

from . import __version__
from .application_assets import check_frontend
from .paths import project_data_root


def doctor():
    # Inspect capabilities without importing/constructing optional model engines.
    from .config import config
    packages = {}
    for name in ('numpy', 'edge-tts', 'openai', 'python-dotenv'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    root = project_data_root()
    ancestor = root
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    data_available = os.access(ancestor, os.W_OK | os.X_OK)
    if root.is_relative_to(Path('/data')) and not os.path.ismount('/data'):
        data_available = False
    return {'version': __version__, 'python': sys.version.split()[0],
        'executable': sys.executable, 'core_dependencies': packages,
        'core_ready': all(packages.values()) and data_available,
        'data': {'root': str(root), 'writable_ancestor': str(ancestor), 'available': data_available},
        'frontend': check_frontend(), 'llm': {'configured': bool(config.llm.api_key),
            'mode': 'configured_not_connectivity_verified' if config.llm.api_key else 'rules_unconfigured'},
        'asr': {'funasr_installed': importlib.util.find_spec('funasr') is not None,
            'faster_whisper_installed': importlib.util.find_spec('faster_whisper') is not None,
            'enabled_by_default': False},
        'external_delivery': {'email': False, 'sms': False, 'phone': False},
        'scope': 'offline inspection; no network/model/device or human acceptance'}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Delegate each application's existing flags and help to its own parser.
    if argv and argv[0] == 'web':
        from .web import main as web_main
        return web_main(argv[1:])
    parser = argparse.ArgumentParser(description='小海：本机记忆与情感虚拟形象')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command')
    check = sub.add_parser('doctor', help='离线检查安装和配置，不调用模型或网络')
    check.add_argument('--require-ui', action='store_true', help='缺少完整网页资源时退出失败')
    sub.add_parser('web', help='启动本机网页；web --help 查看参数')
    text = sub.add_parser('text', help='启动文本交互')
    text.add_argument('--tts', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        result = doctor()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['core_ready'] and (not args.require_ui or result['frontend']['available']) else 1
    if args.command == 'text':
        from .main import Avatar, _repl
        avatar = Avatar()
        try:
            _repl(avatar, use_tts=args.tts)
        finally:
            avatar.close()
        return 0
    parser.print_help()
    return 0
