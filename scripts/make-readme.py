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

## 反向代理必需的两条修正（缺一不可）

上游打包树的 `PACKAGED_CHILD_ENV_ALLOWLIST` 不转发 `OD_ALLOWED_ORIGINS`，
`entry-layout.css` 又在 ≤1080px 把侧栏轨道归零。两者都必须在 nginx 层修，
见本包内 `docs/nginx/od-headless.conf`：

    location / {{
        include /etc/nginx/snippets/od-headless.conf;
        proxy_pass http://127.0.0.1:<portal-port>;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }}

| 修正 | 不做的后果 |
| --- | --- |
| `proxy_set_header Origin ""` | 所有写请求 403，建项目/发消息全失败 |
| `Accept-Encoding ""` + `gzip off` + `sub_filter` | 窄窗侧栏按钮点不动 |

**代价**：daemon 自身的 origin 校验失效，认证必须由 nginx 负责。
证据与升级复验清单见本包内 `docs/UPSTREAM-LIMITATIONS.md`。

## 结构

    out/linux/namespaces/{ns}/assembled/   应用主体（含 web/out 静态导出）
    out/linux/namespaces/{ns}/resources/   bundled node + vela
    runtime/linux/                         运行期数据/状态
    docs/nginx/od-headless.conf            两条必需的反代修正（可直接 include）
    docs/UPSTREAM-LIMITATIONS.md           为何需要这两条，附实测证据
    launcher/open-design-headless-{ns}     启动脚本
""")
print(f"readme written: {dest}")
