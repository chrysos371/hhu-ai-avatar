"""Verify report, registered audit fixes, byte bindings, links and retirement."""
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1]
sys.path.insert(0, str(AUDIT))
from execution_common import ROOT, BASE, RUN, WORK, read, sha, write_new, require, historical, verify_freeze
from verify_execution import retired, manifest_check


def main():
    require(not (HERE / "closeout.json").exists(), "fresh closeout required")
    evidence = read(HERE / "system-evidence.json")
    require(evidence["verified"] and evidence["actual_generation_calls"] == 270
        and not evidence["local_gain_gate_passed"] and evidence["candidate_isolated"], "system evidence differs")
    require(evidence["collector_sha256"] == sha(HERE / "collect_system_evidence.py"), "collector source differs")
    require(all(sha(ROOT / n) == v for n, v in evidence["source_sha256"].items()), "collected source bytes changed")
    verify_freeze(WORK / "freeze-v1.json", evidence["execution_freeze_sha256"])
    for stage in ["before", "train", "reload", "after"]:
        p = RUN / "ledger" / (stage + "-verified.json")
        require(sha(p) == evidence["stages"][stage]["proof_sha256"] == sha(WORK / p.name), "stage proof changed")
        retired(read(RUN / stage / "process-result.json")); manifest_check(read(p))
    adapter = read(HERE / "external-adapter-files.json")
    require(all(sha(RUN / "adapter" / n) == v for n, v in adapter.items()), "adapter changed")
    protocol = read(AUDIT / "工作目录/006-调用结束态核验/verification-protocol-v2.json")
    require(protocol["original_sha256"] == sha(AUDIT / "verify_execution.py")
        and protocol["v2_sha256"] == sha(AUDIT / "工作目录/006-调用结束态核验/verify_execution_v2.py")
        and protocol["transition_validator_sha256"] == sha(AUDIT / "工作目录/006-调用结束态核验/trace_transition.py"), "registered transition verification changed")
    report = AUDIT / "系统审计与推进报告.html"
    meta = read(HERE / "report-render-metadata.json"); browser = read(HERE / "report-browser.json")
    require(meta["system_evidence_sha256"] == sha(HERE / "system-evidence.json")
        and meta["builder_sha256"] == sha(HERE / "build_report.py")
        and meta["HTML_sha256"] == sha(report) and meta["MD_sha256"] == sha(report.with_suffix(".md")), "report binding differs")
    require(browser["completed"] and not browser["errors"] and browser["reportSha256"] == sha(report)
        and browser["scriptSha256"] == sha(AUDIT / "preview_report.mjs"), "browser proof differs")
    require([v["viewport"]["width"] for v in browser["views"]] == [1440, 390], "viewports differ")
    require(meta["tables"] == 2 and meta["links"] == 26, "report structure differs")
    for view in browser["views"]:
        require(not view["overflow"] and view["tableCount"] == 2 and len(view["links"]) == 26
            and all(t["lastCellReadable"] for t in view["horizontalTables"])
            and sha(Path(view["screenshot"])) == view["screenshotSha256"], "report display differs")
    issues = sorted((AUDIT / "问题单").glob("*.md")); require(len(issues) == 8, "issue count differs")
    statuses = {}
    for p in issues:
        status = next(line for line in p.read_text().splitlines() if line.startswith("状态："))
        require(("限定关闭" in status) if p.name[:3] in ["001", "002", "003", "008"] else ("开放" in status), "issue status differs")
        statuses[p.name[:3]] = status
    scan = subprocess.run(["rg", "--files", "--hidden", "--no-ignore", "-g", "*.pyc", "docs", "src", "scripts", "tests"], cwd=ROOT, capture_output=True, text=True)
    require(scan.returncode == 1 and not scan.stdout and not scan.stderr, "repository-local bytecode remains")
    relocation = read(HERE / "local-bytecode-relocation-v1.json")
    require(len(relocation["files"]) == 2 and all(not (ROOT / item["source"]).exists()
        and sha(Path(item["destination"])) == item["sha256"] for item in relocation["files"]), "central cache relocation differs")
    checker = BASE.parent / "cycle-38/审计/check_research_names.py"
    spec = importlib.util.spec_from_file_location("c38_pure_names_final_c52", checker)
    names = importlib.util.module_from_spec(spec); spec.loader.exec_module(names)
    undefined = {str(p.relative_to(ROOT)): names.undefined_globals(p.read_text(), str(p)) for p in AUDIT.rglob("*.py")}
    require(all(not v for v in undefined.values()), "undefined audit names: " + str({k:v for k,v in undefined.items() if v}))
    maintained = [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "experiments/style/README.md", ROOT / "docs/backend.md",
        ROOT / "docs/本机数据布局.md", BASE.parent / "远期目标与验收路线.md"]
    links = []
    for path in list(BASE.rglob("*.md")) + maintained:
        for raw in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            target = raw.split("#", 1)[0].strip("<>")
            if not target or re.match("[a-z]+://", target): continue
            require((path.parent / unquote(target)).resolve().is_file(), "broken link: " + str(path) + ":" + target)
            links.append({"source": str(path.relative_to(ROOT)), "target": raw})
    authors = subprocess.check_output(["git", "log", "f9062234..HEAD", "--format=%an <%ae>"], cwd=ROOT, text=True).splitlines()
    require(authors and set(authors) == {"spinner-bot <langxibielangle@qq.com>"}, "authors differ")
    current = {str(p.relative_to(ROOT)): sha(p) for p in BASE.rglob("*") if p.is_file()}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(historical(head, current) == current, "commit all final C52 files first")
    write_new(HERE / "closeout.json", {"verified": True, "scope": "final engineering/report audit; candidate failed semantic gate",
        "head": head, "verifier_sha256": sha(Path(__file__)), "system_sha256": sha(HERE / "system-evidence.json"),
        "HTML_sha256": sha(report), "MD_sha256": sha(report.with_suffix(".md")), "browser_sha256": sha(HERE / "report-browser.json"),
        "MD_links_checked": len(links), "links": links, "HTML_links": 26, "tables": 2, "viewports": [1440, 390],
        "undefined_globals": undefined, "issue_statuses": statuses, "issues_limited_closed": 4, "issues_open": 4,
        "authors_checked": len(authors), "C52_committed_files_before_closeout": len(current), "repository_local_pyc": 0,
        "actual_model_generations": 270, "new_model_generations_by_this_verifier": 0,
        "candidate_isolated": True, "default_model_changed": False, "overall_goal_active": True})
    print("C52 final report/source/retirement verified:", len(links), "MD links;2tables/26HTMLlinks/1440+390;4limited closed/4open;0localpyc")


if __name__ == "__main__": main()
