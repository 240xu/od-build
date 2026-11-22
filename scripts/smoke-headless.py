#!/usr/bin/env python3
"""解包后直接起 launcher，判定 headless 是否真能启动。

只判定**真实失败特征**，不用宽泛的 "not found" —— 那会误杀正常日志。
成功判据：exit 0（官方主进程 print URL 后自行 return）或 124（超时仍在跑），
且日志里没有下列任一特征。
"""
import os
import pathlib
import re
import signal
import subprocess
import sys
import tarfile
import tempfile

tarball, ns = sys.argv[1], sys.argv[2]
FAIL_PATTERNS = [
    r"Cannot find module",
    r"ERR_MODULE_NOT_FOUND",
    r"failed to resolve",
    r"failed to resolve @open-design/web package root",
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
    # 官方 headless 正常路径是 exit 0（主进程打印 URL 后自行 return）。
    # 90 秒还没退出 = sidecar 永不就绪的挂死状态，必须判失败 ——
    # 之前的实现把 124 也当通过，坏产物能混进 release。
    timed_out = False
    try:
        with open(log, "wb") as fh:
            proc = subprocess.Popen(
                [str(launcher)], stdout=fh, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                code = proc.wait(timeout=90)
            except subprocess.TimeoutExpired:
                timed_out = True
                code = 124
    finally:
        # 官方主进程 return 后 supervisor 会被 reparent 到 init，必须按进程组清干净，
        # 否则 CI runner 上留孤儿进程。
        try:
            subprocess.run(["pkill", "-9", "-f", f"open-design-headless-{ns}"],
                           check=False)
            if "proc" in dir() and proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
    text = log.read_text(errors="ignore")
    print(f"launcher exit={code}")
    print("--- tail ---")
    print("\n".join(text.splitlines()[-40:]))

    hits = [p for p in FAIL_PATTERNS if re.search(p, text)]
    if hits:
        print("FAIL: matched failure signatures:", hits)
        sys.exit(1)
    if timed_out:
        print("FAIL: launcher did not exit within 90s (sidecar never became ready)")
        sys.exit(1)
    if code != 0:
        print(f"FAIL: unexpected exit code {code} (expected 0)")
        sys.exit(1)
    print("SMOKE PASS")
