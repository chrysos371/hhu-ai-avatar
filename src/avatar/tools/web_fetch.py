"""Bounded public HTTP reader with pinned destination IPs and verified TLS."""
from __future__ import annotations

import base64
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import getproxies


def public_url(url: str) -> str:
    if not isinstance(url, str) or not url or len(url) > 2048 or any(c.isspace() or ord(c) < 32 for c in url) or '\\' in url:
        raise ValueError('URL 必须是有效的公开 HTTP(S) 地址。')
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username is not None or p.password is not None:
        raise ValueError('只允许不含登录凭据的 HTTP(S) 地址。')
    host = p.hostname.rstrip('.').encode('idna').decode().lower()
    if p.port not in (None, 80, 443) or host in ('localhost',) or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('不允许本机、内网或非网页端口。')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if '.' not in host or host.replace('.', '').isdigit() or '%' in host:
            raise ValueError('不允许本机或非公开主机名。')
    else:
        if not address.is_global:
            raise ValueError('不允许本机或内网地址。')
    netloc = '[' + host + ']' if ':' in host else host
    if p.port is not None:
        netloc += ':' + str(p.port)
    return urlunsplit((p.scheme, netloc, p.path or '/', p.query, ''))


def public_addresses(addresses: list[str]) -> list[str]:
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError('域名解析到了非公网地址，拒绝读取。')
    return sorted(set(addresses), key=lambda a: (':' in a, a))


def system_proxy() -> str | None:
    # This is local administrator configuration, never a tool argument.
    import os
    return os.getenv('AVATAR_WEB_PROXY') or getproxies().get('https')


def _request(url, addresses, *, timeout=10, max_bytes=1_000_000, accept='text/html,text/plain,application/json', proxy=None):
    p = urlsplit(url)
    port = p.port or (443 if p.scheme == 'https' else 80)
    deadline = time.monotonic() + timeout
    address = addresses[0]
    if proxy:
        config = urlsplit(proxy)
        if config.scheme != 'http' or not config.hostname:
            raise ValueError('当前网页读取仅支持 HTTP CONNECT 代理。')
        conn = http.client.HTTPConnection(config.hostname, config.port or 80, timeout=timeout)
        headers = {}
        if config.username is not None:
            auth = unquote(config.username) + ':' + unquote(config.password or '')
            headers['Proxy-Authorization'] = 'Basic ' + base64.b64encode(auth.encode()).decode()
        conn.set_tunnel(address, port, headers=headers)
    else:
        conn = http.client.HTTPConnection(address, port, timeout=timeout)
    try:
        conn.connect()
        if p.scheme == 'https':
            conn.sock = ssl.create_default_context().wrap_socket(conn.sock, server_hostname=p.hostname)
        host = '[' + p.hostname + ']' if ':' in p.hostname else p.hostname
        if p.port:
            host += ':' + str(p.port)
        conn.request('GET', urlunsplit(('', '', p.path or '/', p.query, '')),
                     headers={'Host': host, 'User-Agent': 'HHU-Avatar/0.1', 'Accept': accept,
                              'Accept-Encoding': 'identity', 'Connection': 'close'})
        response = conn.getresponse()
        if response.status in (301, 302, 303, 307, 308):
            return response.status, response.headers, b''
        if response.status != 200:
            raise ValueError(f'网页返回 HTTP {response.status}，未获得可读正文。')
        if response.getheader('Content-Encoding', 'identity').lower() not in ('identity', ''):
            raise ValueError('服务器未提供未压缩正文，拒绝解压不受控内容。')
        data = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('网页读取超时。')
            if conn.sock:
                conn.sock.settimeout(remaining)
            block = response.read1(min(65536, max_bytes + 1 - len(data)))
            if not block:
                break
            data.extend(block)
            if len(data) > max_bytes:
                raise ValueError('网页超过1MB读取上限。')
        return response.status, response.headers, bytes(data)
    finally:
        conn.close()


def resolve_public(host: str, proxy=None) -> list[str]:
    addresses = list({r[4][0] for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    fake = ipaddress.ip_network('198.18.0.0/15')
    if addresses and proxy and all(ipaddress.ip_address(a) in fake for a in addresses):
        # Clash fake-IP mapping is not a public destination. Resolve via DoH,
        # then CONNECT to the verified IP, not to the hostname/proxy DNS.
        url = 'https://1.1.1.1/dns-query?name=' + quote(host, safe='') + '&type=A'
        status, _, data = _request(url, ['1.1.1.1'], proxy=proxy, max_bytes=20000, accept='application/dns-json')
        if status != 200:
            raise ValueError('公共 DNS 解析失败。')
        answer = json.loads(data)
        addresses = [r['data'] for r in answer.get('Answer', []) if r.get('type') == 1]
    return public_addresses(addresses)


class _Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.text, self.title = [], [], []
        self.hidden_depth = self.title_depth = self.tags = 0
    def handle_starttag(self, tag, attrs):
        self.tags += 1
        if len(self.stack) >= 128 or self.tags > 20000:
            raise ValueError('网页嵌套层级或标签数量超过解析上限。')
        attrs = dict(attrs)
        hidden = (tag in ('script', 'style', 'noscript', 'nav', 'footer', 'aside', 'head', 'template', 'iframe')
                  or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
                  or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden', attrs.get('style') or '', re.I))
        if tag not in ('meta', 'link', 'br', 'hr', 'img', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'):
            self.stack.append((tag, bool(hidden)))
            self.hidden_depth += bool(hidden)
            self.title_depth += tag == 'title'
        if tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'article', 'section', 'tr'):
            self.text.append('\n')
    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for removed_tag, hidden in self.stack[i:]:
                    self.hidden_depth -= hidden
                    self.title_depth -= removed_tag == 'title'
                del self.stack[i:]
                break
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'section', 'article'):
            self.text.append('\n')
    def handle_data(self, data):
        if self.title_depth:
            self.title.append(data)
        elif not self.hidden_depth:
            self.text.append(data)


def extract_text(html: str, *, max_chars: int = 4000) -> dict:
    if type(max_chars) is not int or not 200 <= max_chars <= 8000:
        raise ValueError('正文长度必须在200～8000字符之间。')
    parser = _Document()
    parser.feed(html)
    text = '\n'.join(line.strip() for line in re.sub(r'[ \t\r\f\v]+', ' ', ''.join(parser.text)).splitlines() if line.strip())
    return {'title': re.sub(r'\s+', ' ', ''.join(parser.title)).strip()[:240],
            'text': text[:max_chars], 'truncated': len(text) > max_chars}


def read_webpage(url: str, max_chars: int = 4000) -> dict:
    url = public_url(url)
    if type(max_chars) is not int or not 200 <= max_chars <= 8000:
        raise ValueError('正文长度必须在200～8000字符之间。')
    proxy = system_proxy()
    for _ in range(4):
        p = urlsplit(url)
        addresses = resolve_public(p.hostname, proxy)
        for address in addresses[:2]:
            try:
                status, headers, data = _request(url, [address], proxy=proxy, timeout=8)
                break
            except (OSError, TimeoutError) as error:
                last_error = error
        else:
            raise RuntimeError('网页连接未成功（' + type(last_error).__name__ + '），请稍后重试。') from None
        if status in (301, 302, 303, 307, 308):
            location = headers.get('Location')
            if not location:
                raise ValueError('网页跳转缺少目标地址。')
            url = public_url(urljoin(url, location))
            continue
        content_type = headers.get_content_type()
        if content_type not in ('text/html', 'application/xhtml+xml', 'text/plain', 'text/markdown', 'application/json'):
            raise ValueError('仅支持 HTML、文本和 JSON 网页，不下载附件。')
        encoding = headers.get_content_charset() or 'utf-8'
        try:
            text = data.decode(encoding, errors='replace')
        except LookupError:
            text = data.decode('utf-8', errors='replace')
        page = extract_text(text, max_chars=max_chars) if content_type in ('text/html', 'application/xhtml+xml') else dict(title=p.hostname, text=text[:max_chars], truncated=len(text) > max_chars)
        if not page['text'].strip():
            raise ValueError('网页没有可提取正文，可能需要 JavaScript 或登录。')
        return dict(page, url=url, fetched_at=time.time(), content_type=content_type, untrusted=True)
    raise ValueError('网页跳转次数超过上限。')
