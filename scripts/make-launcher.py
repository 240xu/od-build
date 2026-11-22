#!/usr/bin/env python3
"""生成官方风格的 headless launcher。

关键点（都是实际踩过的坑）：
  1. ROOT 必须解析符号链接。launcher 常被 ~/.local/bin 软链调用，
     dirname("$0") 会给出 ~/.local/bin，ROOT 就算成 ~/.local。
  2. 只上一级：launcher 位于 <root>/launcher/。
"""
import pathlib
import sys

ns = sys.argv[1]
outdir = pathlib.Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)

tmpl = """#!/bin/sh
# Open Design headless launcher — namespace: {NS}
# 由 opendesign-linux CI 生成。ROOT 为本 bundle 解压目录，可用 OD_ROOT 覆盖。
#
# 解析符号链接：launcher 常被 ~/.local/bin 软链调用，$0 不是真实路径。
SELF="$0"
while [ -L "$SELF" ]; do
  TARGET=$(readlink "$SELF")
  case "$TARGET" in
    /*) SELF="$TARGET" ;;
    *)  SELF="$(dirname "$SELF")/$TARGET" ;;
  esac
done
ROOT="${{OD_ROOT:-$(cd "$(dirname "$SELF")/.." && pwd)}}"
RES="$ROOT/out/linux/namespaces/{NS}/resources/open-design"
ENTRY="$ROOT/out/linux/namespaces/{NS}/assembled/app/node_modules/@open-design/packaged/dist/headless.mjs"
OPEN_DESIGN_AMR_ENDPOINT_BINDING='' \\
OD_PACKAGED_NAMESPACE="{NS}" \\
OD_DATA_DIR="$ROOT/runtime/linux" \\
OD_RESOURCE_ROOT="$RES" \\
  exec "$RES/bin/node" "$ENTRY" "$@"
"""

target = outdir / f"open-design-headless-{ns}"
target.write_text(tmpl.format(NS=ns))
target.chmod(0o755)
print(f"launcher written: {target}")
