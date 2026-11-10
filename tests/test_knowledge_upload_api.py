import http.client
import json
from urllib.parse import quote
import pytest
from test_web_api_v1 import api_v1


def upload(server, filename, body, mime="text/plain", declared=None):
    c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    c.putrequest(
        "POST", "/api/v1/knowledge/preview-file?filename=" + quote(filename, safe="")
    )
    c.putheader("X-Avatar-Token", server.token)
    c.putheader("Content-Type", mime)
    c.putheader("Content-Length", len(body) if declared is None else declared)
    c.endheaders()
    if declared is None:
        c.send(body)
    r = c.getresponse()
    result = r.status, json.loads(r.read())
    c.close()
    return result


@pytest.mark.parametrize(
    "filename,body,mime",
    [
        ("../private.txt", b"text", "text/plain"),
        ("notes.exe", b"text", "text/plain"),
        ("notes.txt", b"\xff\xfe", "text/plain"),
        ("notes.txt", b"a\x00b", "text/plain"),
        ("notes.txt", b"hello", "text/html"),
        ("notes.md", b"hello", "text/plain"),
    ],
)
def test_reject_bad_upload_without_knowledge_write(api_v1, filename, body, mime):
    request, server = api_v1
    assert upload(server, filename, body, mime)[0] == 422
    assert request("/api/v1/knowledge/sources")[1]["data"] == []


def test_size_rejected_before_read_and_valid_utf8_preview(api_v1):
    request, server = api_v1
    assert upload(server, "large.txt", b"", declared=5 * 1024 * 1024 + 1)[0] == 422
    code, data = upload(
        server, "notes.md", "# 标题\n\n一些明确知识。".encode(), "text/markdown"
    )
    assert code == 201 and data["data"]["preview"]["accepted"]
    assert request("/api/v1/knowledge/sources")[1]["data"] == []
