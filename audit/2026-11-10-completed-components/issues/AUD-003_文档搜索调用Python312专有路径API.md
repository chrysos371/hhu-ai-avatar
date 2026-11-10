# AUD-003 · 文档搜索调用 Python 3.12 才提供的路径 API

- **等级：** P1 · 高（受支持环境中的功能中断）
- **类别：** Python 版本兼容
- **状态：** 静态 API/调用点确认；未切换解释器运行
- **置信度：** 高

## 摘要

项目声明支持 Python `>=3.10`，但本机授权资料搜索在遍历每个子目录时无条件调用 `Path.is_junction()`。Python 官方文档标明该方法从 Python 3.12 才加入。因此在 Python 3.10/3.11 中，只要白名单目录包含子目录，列表推导会触发 `AttributeError`，MCP 搜索工具失败。

## 证据

- `pyproject.toml` 声明 `requires-python = ">=3.10"`。
- `src/avatar/tools/local_tools.py:18-19` 遍历子目录时直接调用 `(Path(directory)/d).is_junction()`，没有版本保护或兼容封装。
- `src/avatar/tools/assistant_server.py:12` 注册该 `search_documents` 函数为可调用工具。
- 当前 `tests/test_local_tools.py` 只在运行解释器上检查平面目录文件，不覆盖含子目录的 Python 3.10/3.11 环境。
- Python 官方文档说明 [`Path.is_junction()` 于 Python 3.12 新增](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.is_junction)。

## 影响

在项目明确支持的 Python 3.10/3.11 用户环境中，资料目录只要有普通子目录，搜索就会在扫描阶段失败。顶层文件搜索仍可能工作，因此平面测试目录无法发现此问题。

## 建议

1. 使用跨版本的 `os.path`/Windows 属性兼容函数检测 junction，或在较低版本跳过 junction 检测并通过 `resolve().is_relative_to(root)` 阻止越界。
2. 为 Python 3.10/3.11 增加“白名单根目录含普通子目录、含 junction/符号链接”的兼容验证。
3. 建立多 Python 版本 CI，至少覆盖项目声明的最低版本与当前版本。

## 验收建议

- Python 3.10、3.11、3.12+ 下，普通子目录中的授权文本可搜索。
- 符号链接或 junction 指向白名单外的内容不会被读出。
- 不支持 junction API 的平台不会因属性缺失而让整个搜索失败。

## 参考位置

- [项目 Python 版本声明](../../../pyproject.toml)
- [资料搜索实现](../../../src/avatar/tools/local_tools.py)
- [资料搜索测试](../../../tests/test_local_tools.py)
- [Python 3.12 pathlib 文档](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.is_junction)
