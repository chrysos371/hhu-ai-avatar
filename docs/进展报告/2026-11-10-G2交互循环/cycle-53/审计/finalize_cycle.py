"""Verify then separately seal committed C53 audit/report bytes."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

from avatar.lab.common import sha, write_json
from run_python_regression import ROOT, BASE, snapshot

AUDIT=BASE/"审计"
OUT=AUDIT/"收尾核验"


def read(p):return json.loads(Path(p).read_text())

def archive(ref,names):
    path=BASE.parent/"cycle-52/审计/execution_common.py"
    spec=importlib.util.spec_from_file_location("c52_pure_archive_c53_final",path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.historical(ref,names)


def main(seal):
    if seal:
        target=AUDIT/"证据清单.json"
        assert not target.exists() and read(OUT/"closeout.json")["verified"]
        assert not subprocess.check_output(["git","status","--porcelain","--",str(BASE)],cwd=ROOT)
        files={str(p.relative_to(BASE)):sha(p) for p in sorted(BASE.rglob("*")) if p.is_file()}
        names={str((BASE/n).relative_to(ROOT)):v for n,v in files.items()}
        assert archive("HEAD",names)==names and not any("__pycache__" in n for n in files)
        write_json(target,files)
        print("C53 sealed",len(files),"files;SHA",sha(target),";0newLLM/GPU;2issues open;goal active")
        return
    assert not (OUT/"closeout.json").exists()
    system=read(OUT/"system-evidence.json")
    assert system["verified"] and system["collector_sha256"]==sha(AUDIT/"collect_evidence.py")
    assert all(sha(ROOT/n)==v for n,v in system["source_sha256"].items())
    regression=read(AUDIT/"工作目录/004-当前软件回归/python-first-binding.json")
    assert snapshot()==regression["source_git_sha256"] and len(snapshot())==494
    assert system["new_LLM_generations"]==system["new_training_steps"]==system["GPU_allocations"]==0
    meta=read(OUT/"report-render-metadata.json");browser=read(OUT/"report-browser.json")
    report=AUDIT/"系统审计与推进报告.html"
    assert meta["system_evidence_sha256"]==sha(OUT/"system-evidence.json") and meta["builder_sha256"]==sha(AUDIT/"build_report_v2.py")
    assert meta["HTML_sha256"]==sha(report) and meta["MD_sha256"]==sha(report.with_suffix(".md"))
    assert browser["completed"] and not browser["errors"] and browser["reportSha256"]==sha(report)
    assert browser["scriptSha256"]==sha(AUDIT/"preview_report_v2.mjs")
    assert meta["tables"]==2 and meta["links"]==14
    assert [v["viewport"]["width"] for v in browser["views"]]==[1440,390]
    assert all(not v["overflow"] and v["tableCount"]==2 and len(v["links"])==14
        and all(t["lastCellReadable"] for t in v["horizontalTables"])
        and sha(Path(v["screenshot"]))==v["screenshotSha256"] for v in browser["views"])
    issues=sorted((AUDIT/"问题单").glob("*.md"));assert len(issues)==4
    for p in issues:
        status=next(line for line in p.read_text().splitlines() if line.startswith("状态："))
        assert ("限定关闭" in status) if p.name[:3] in ("003","004") else ("开放" in status)
    checker=BASE.parent/"cycle-38/审计/check_research_names.py"
    spec=importlib.util.spec_from_file_location("c38_names_c53_final",checker);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    undefined={str(p.relative_to(ROOT)):module.undefined_globals(p.read_text(),str(p)) for p in AUDIT.glob("*.py")}
    assert all(not v for v in undefined.values()),undefined
    scan=subprocess.run(["rg","--files","--hidden","--no-ignore","-g","*.pyc","docs","src","scripts","tests"],cwd=ROOT,capture_output=True,text=True)
    assert scan.returncode==1 and not scan.stdout and not scan.stderr
    maintained=[ROOT/"AGENTS.md",ROOT/"README.md",ROOT/"experiments/style/README.md",ROOT/"docs/backend.md",ROOT/"docs/本机数据布局.md",BASE.parent/"远期目标与验收路线.md"]
    links=[]
    for path in list(BASE.rglob("*.md"))+maintained:
        for raw in re.findall(r"\[[^\]]*\]\(([^)]+)\)",path.read_text()):
            target=raw.split("#",1)[0].strip("<>")
            if not target or re.match("[a-z]+://",target):continue
            assert (path.parent/unquote(target)).resolve().is_file(),(str(path),target)
            links.append({"source":str(path.relative_to(ROOT)),"target":raw})
    authors=subprocess.check_output(["git","log","f949269a..HEAD","--format=%an <%ae>"],cwd=ROOT,text=True).splitlines()
    assert authors and set(authors)=={"spinner-bot <langxibielangle@qq.com>"}
    files={str(p.relative_to(ROOT)):sha(p) for p in BASE.rglob("*") if p.is_file()}
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip();assert archive(head,files)==files
    write_json(OUT/"closeout.json",{"verified":True,"scope":"final current loader repair/CPU/report verification;no causal or model-quality approval",
        "head":head,"verifier_sha256":sha(Path(__file__)),"system_sha256":sha(OUT/"system-evidence.json"),
        "MD_sha256":sha(report.with_suffix(".md")),"HTML_sha256":sha(report),"browser_sha256":sha(OUT/"report-browser.json"),
        "MD_links_checked":len(links),"links":links,"tables":2,"HTML_links":14,"viewports":[1440,390],"undefined_globals":undefined,
        "authors_checked":len(authors),"issues_limited_closed":2,"issues_open":2,"new_LLM_generations":0,"new_training_steps":0,
        "GPU_allocations":0,"step_logging_actual_GPU_unverified":True,"default_model_changed":False,"goal_active":True})
    print("C53 closeout:",len(links),"MD links;2tables/14HTMLlinks/1440+390;2limited closed/2open;0newLLM/GPU")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--seal",action="store_true");main(parser.parse_args().seal)
