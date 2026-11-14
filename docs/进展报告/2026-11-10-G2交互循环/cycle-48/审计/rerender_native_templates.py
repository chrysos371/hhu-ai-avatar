"""Native-environment Jinja replay only; no Llama import or model construction."""
import argparse
import hashlib
import json
from pathlib import Path

from jinja2 import Environment, StrictUndefined
from avatar.lab.native_tool_wire import template_messages, request_tools


def main(template_path,requests_path):
    env = Environment(undefined=StrictUndefined)
    def fail(message): raise ValueError(message)
    env.globals['raise_exception'] = fail
    template = env.from_string(template_path.read_text())
    hashes = []
    for line in requests_path.read_text().splitlines():
        data = json.loads(line)['request']
        prompt = template.render(messages=template_messages(data['messages']),
            tools=request_tools(data,enabled=False),add_generation_prompt=True,
            enable_thinking=False,bos_token='',eos_token='')
        assert prompt.endswith('<think>\n\n</think>\n\n')
        hashes.append(hashlib.sha256(prompt.encode()).hexdigest())
    print(json.dumps(hashes))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template',type=Path,required=True)
    parser.add_argument('--requests',type=Path,required=True)
    args = parser.parse_args(); main(args.template,args.requests)
