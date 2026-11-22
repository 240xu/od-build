#!/usr/bin/env python3
"""解包后直接起 launcher，判定 headless 是否真能启动。

只判定**真实失败特征**，不用宽泛的 "not found" —— 那会误杀正常日志。
成功判据：exit 0（官方主进程 print URL 后自行 return）或 124（超时仍在跑），
且日志里没有下列任一特征。
"""
import re
import subprocess
import sys
import tarfile
import tempfile
import pathlib

tarball, ns = sys.argv[1], sys.argv[2]
FAIL_PATTERNS = [
    r"Cannot find module",
    r"ERR_MODULE_NOT_FOUND",
    r"failed to resolve",
    r"Failed to load next.config",
    r"ENOENT.*layout\.tsx",
    r"exited before a generation became ready",
    r"exec: .*: not found",
]

with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    with tarfile.open(tarball) as t:
        t.extractall(d)
    launcher = d / "launcher" / f"open-design-headless-{ns}"
    launcher.chmod(0o755)
    log = d / "run.log"
    try:
        with open(log, "wb") as fh:
            code = subprocess.run(
                [str(launcher)], stdout=fh, stderr=subprocess.STDOUT,
                timeout=90,
            ).returncode
    except subprocess.TimeoutExpired:
        code = 124
    text = log.read_text(errors="ignore")
    print(f"launcher exit={code}")
    print("--- tail ---")
    print("\n".join(text.splitlines()[-40:]))

    hits = [p for p in FAIL_PATTERNS if re.search(p, text)]
    if hits:
        print("FAIL: matched failure signatures:", hits)
        sys.exit(1)
    if code not in (0, 124):
        print(f"FAIL: unexpected exit code {code}")
        sys.exit(1)
    print("SMOKE PASS")
