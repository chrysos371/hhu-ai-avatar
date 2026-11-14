"""Final C51 report, byte binding, display, documentation and author verification."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

from avatar.lab.common import sha
from run_python_regression import ROOT, BASE, snapshot


def read(path):
    return json.loads(Path(path).read_text())


def main():
    out = BASE / "审计/收尾核验/closeout.json"
    assert not out.exists()
    system_path = out.with_name("system-evidence.json")
    system = read(system_path)
    assert system["verified"] and system["verifier_sha256"] == sha(BASE / "审计/collect_closeout.py")
    assert all(sha(ROOT / name) == value for name, value in system["source_sha256"].items())
    regression = read(BASE / "审计/工作目录/002-当前软件回归/python-first-binding.json")
    assert snapshot() == regression["source_git_sha256"] and len(snapshot()) == 493
    assert system["new_native_generations"] == system["training_steps"] == 0
    assert system["semantic_quality_approved"] is False and system["default_model_changed"] is False
    meta = read(BASE / "审计/report-render-metadata.json")
    browser = read(BASE / "审计/收尾核验/report-browser.json")
    report = BASE / "审计/系统审计与推进报告.html"
    assert meta["system_evidence_sha256"] == sha(system_path)
    assert meta["builder_sha256"] == sha(BASE / "审计/build_report.py")
    assert meta["HTML_sha256"] == sha(report) and meta["MD_sha256"] == sha(report.with_suffix(".md"))
    assert browser["completed"] and not browser["errors"] and browser["reportSha256"] == sha(report)
    assert browser["scriptSha256"] == sha(BASE / "审计/preview_report.mjs")
    assert [view["viewport"]["width"] for view in browser["views"]] == [1440, 390]
    assert all(not view["overflow"] and view["tableCount"] == meta["tables"] == 2
        and len(view["links"]) == meta["links"] == 25 for view in browser["views"])
    assert all(table["lastCellReadable"] for view in browser["views"] for table in view["horizontalTables"])
    assert all(sha(Path(view["screenshot"])) == view["screenshotSha256"] for view in browser["views"])
    issues = sorted((BASE / "审计/问题单").glob("*.md"))
    assert len(issues) == 6 and all("限定关闭" in p.read_text().splitlines()[2] for p in issues)
    related = BASE.parent / "cycle-52/审计/问题单/001-CLI导入失败被误当门禁拒绝.md"
    assert "限定关闭" in related.read_text() and "撤回" in related.read_text()
    checker = BASE.parent / "cycle-38/审计/check_research_names.py"
    spec = importlib.util.spec_from_file_location("old_pure_names", checker)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scripts = list((BASE / "审计").glob("*.py")) + list((BASE.parent / "cycle-52/审计").glob("*.py"))
    undefined = {str(p.relative_to(ROOT)): module.undefined_globals(p.read_text(), str(p)) for p in scripts}
    assert all(not value for value in undefined.values()), undefined
    maintained = [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "experiments/style/README.md",
        ROOT / "docs/backend.md", ROOT / "docs/本机数据布局.md", BASE.parent / "远期目标与验收路线.md"]
    links = []
    for path in list(BASE.rglob("*.md")) + list((BASE.parent / "cycle-52").rglob("*.md")) + maintained:
        for raw in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            target = raw.split("#", 1)[0].strip("<>")
            if not target or re.match("[a-z]+://", target):
                continue
            assert (path.parent / unquote(target)).resolve().is_file(), (str(path), target)
            links.append({"source": str(path.relative_to(ROOT)), "target": raw})
    authors = subprocess.check_output(["git", "log", "08ac8187..HEAD", "--format=%an <%ae>"], cwd=ROOT, text=True).splitlines()
    assert authors and set(authors) == {"spinner-bot <langxibielangle@qq.com>"}
    old_paths = [str(BASE.parent / f"cycle-{n:02}") for n in range(3, 51)]
    old_paths.append(str(ROOT / "docs/进展报告/2026-11-12-项目数据集中迁移"))
    assert not subprocess.check_output(["git", "diff", system["head"], "--name-only", "--", *old_paths], cwd=ROOT)
    assert not subprocess.check_output(["git", "status", "--porcelain", "--", *old_paths], cwd=ROOT)
    result = {"verified": True, "scope": "final scoped preparation/report verification;no model-quality approval",
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "verifier_sha256": sha(Path(__file__)), "system_sha256": sha(system_path),
        "HTML_sha256": sha(report), "MD_sha256": sha(report.with_suffix(".md")),
        "browser_sha256": sha(BASE / "审计/收尾核验/report-browser.json"),
        "HTML_tables": 2, "HTML_links": 25, "viewports": [1440, 390],
        "MD_links_checked": len(links), "links": links, "undefined_globals": undefined,
        "issues_limited_closed": 6, "related_C52_false_positive_limited_closed": True,
        "old_seals_verified_in_system_collection": 49, "old_items": 12072,
        "old_sealed_paths_unchanged_since_system_collection": True,
        "authors_checked": len(authors), "maintained_docs_sha256": {str(p.relative_to(ROOT)): sha(p) for p in maintained},
        "new_model_generations": 0, "training_steps": 0, "default_model_changed": False,
        "human_physical_or_general_quality_approved": False, "overall_goal_active": True}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("C51 final closeout:", len(links), "MD links;2tables/25HTMLlinks/1440+390;6issues limited closed;0 models/training")


if __name__ == "__main__":
    main()
