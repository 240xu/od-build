#!/usr/bin/env python3
"""生成 bundle 内 README。"""
import pathlib
import sys

ns = sys.argv[1]
dest = pathlib.Path(sys.argv[2])

dest.write_text(f"""# OpenDesign headless bundle ({ns})

纯 headless 运行集：daemon + web，**无 Electron**。

## 部署

    tar -xzf od-headless-{ns}.tar.gz -C ~/od-stable
    ~/od-stable/launcher/open-design-headless-{ns}

启动后 daemon/web 监听 `127.0.0.1` 动态端口；用官方 status IPC 查实际 URL。
数据落在 `runtime/linux`。

**保活注意**：官方 headless 主进程打印 URL 后会主动 return（supervisor 被
reparent 到 init），因此 systemd 直接用 `Type=simple` 跑 launcher 会看到
「主进程正常退出」并连带 SIGKILL 整棵 cgroup。需要包装脚本盯住 sidecar
状态 IPC 维持存活。

## 结构

    out/linux/namespaces/{ns}/assembled/   应用主体（含 web/out 静态导出）
    out/linux/namespaces/{ns}/resources/   bundled node + vela
    runtime/linux/                         运行期数据/状态
    launcher/open-design-headless-{ns}     启动脚本
""")
print(f"readme written: {dest}")
