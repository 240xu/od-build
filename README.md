# opendesign-linux

在 GitHub Actions 上构建 [OpenDesign](https://github.com/nexu-io/open-design) 的 **Linux 两种产物**，并在同一个 release 里发布：

| 产物 | 内容 | 用途 |
|---|---|---|
| `od-headless-<ns>.tar.gz` | daemon + web，**不含 Electron** | CLI + 浏览器（服务器部署） |
| `Open Design-<ns>.AppImage` | 桌面版，含 Electron | 有桌面的机器 |

## 为什么需要这个

官方 Linux 只有 Docker 路径，**不发布任何 AppImage / deb / headless 预构建包**
（穷举 40 个 release 共 228 个 asset，零 linux 资产）。

## 触发方式

| 方式 | 说明 |
|---|---|
| **手动** | Actions → Build OpenDesign Linux → Run workflow，可指定上游 ref 与目标 |
| **定时** | 每 6 小时（`cron: 17 */6 * * *`）检查上游最新 release tag；若本仓库还没有对应 tag 的 release，自动构建 |
| **上游发布** | `repository_dispatch` 事件 `upstream-release`（需在 fork 侧配置 webhook） |

定时任务会先比对 `240xu/opendesign-linux` 已有 release tag（`v<version>-<ns>`），
已存在则跳过，避免重复构建。

## 构建哪个 ref（重要）

**`upstream_ref` 留空时只取上游最新 release tag，绝不回退 `main`。**

原因：实测上游 `main` 与 release tag 会 **diverged**（`v0.27.2` 时 `main` 领先 24 个提交、
tag 领先 13 个）。早期版本回退 `main` 的后果是：release 标着 `v0.27.2`，
内容却是 `main` 的后续代码 —— 版本号与内容不对齐，排障时无法判断实际跑的是什么。

想用 `main` 的新修复，**必须显式传** `upstream_ref=main`；此时产物 tag 会自动带
`-main.<sha7>` 后缀（如 `v0.27.3-main.a1b2c3d`），便于溯源。

## 构建期已知坑（都已处理）

1. **`--containerized` 不可用。** 官方 `buildDockerArgs` 不把 `CI` 传进容器，
   容器内无 TTY → `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY` → `docker build exit 1`。
   官方 workflow 注释也写着「等 containerized pnpm bootstrap 修好再启用 Linux lane」。
   → 走非 containerized 原生构建。

2. **`onnxruntime-node` 的 install 钩子会下 CUDA EP 二进制**，受限网络下 404。
   → `ONNXRUNTIME_NODE_INSTALL_CUDA=skip`。

3. **`apps/web/package.json` 的 `files` 不含 `out`**，`pnpm pack` 不带，
   headless 的 web sidecar 走 Next 静态导出。
   → 先 `pnpm --filter @open-design/web build`，打包后补进 assembled。

4. **上游 main 缺 PR #8538。** `next.config.ts` 的 CMS fingerprint 探测写的是
   web 包自己的 `src`，打包后恒为「存在」→ 去读 `WORKSPACE_ROOT/apps/web/app/layout.tsx`
   → ENOENT → next.config 加载失败 → web sidecar exit 1。
   → `scripts/patch-cms-fingerprint.py` 幂等打补丁（上游合并后自动跳过）。
   **桌面版同样需要这个补丁**，否则首次启动就崩。

5. **`tools-pack --dir` 的输出多一层 `out/`。**
   实际是 `<dir>/out/linux/namespaces/<ns>/...`。

6. **launcher 的 ROOT 必须解析符号链接。**
   launcher 常被 `~/.local/bin` 软链调用，`dirname "$0"` 会给出错误目录，
   ROOT 算成 `~/.local`，然后 exec 一个不存在的 node。

## 部署桌面版（AppImage）

```sh
# artifact 经 upload-artifact 中转后不保留可执行位，必须手加
chmod +x Open.Design-stable.AppImage
./Open.Design-stable.AppImage
```

> 注意 GitHub 会把资产名里的空格 sanitize 成点号：
> `Open Design-stable.AppImage` → **`Open.Design-stable.AppImage`**。

## 部署 headless

```sh
tar -xzf od-headless-stable.tar.gz -C ~/od-stable
~/od-stable/launcher/open-design-headless-stable
```

**保活注意**：官方 headless 主进程打印 URL 后会主动 return（supervisor 被
reparent 到 init），systemd 用 `Type=simple` 直接跑 launcher 会看到「主进程
正常退出」并连带 SIGKILL 整棵 cgroup。需要包装脚本盯住 sidecar 状态 IPC。

## 本仓库不含任何部署侧配置

认证门、fail2ban、nginx 注入、token 等全部留在部署主机，**不进此仓库**。

## 脚本

| 文件 | 作用 |
|---|---|
| `scripts/patch-cms-fingerprint.py` | 应用 PR #8538（幂等） |
| `scripts/make-launcher.py` | 生成官方风格 launcher（解析符号链接） |
| `scripts/make-readme.py` | 生成 bundle 内 README |
| `scripts/smoke-headless.py` | 解包实跑，只判真实失败特征 |

---

## 自动构建：为什么不靠 GitHub 原生事件

**上游 release 事件无法直接触发本仓库的 workflow。** GitHub webhook 是仓库作用域的，
不能跨仓库投递；在上游 org 装 webhook 需要该 org 的 admin 权限。`workflow_run` /
`workflow_call` 也只在同一仓库内生效。

所以「上游更新即自动构建」必须靠**外部调度器轮询**，本机（wuming）已落地
systemd timer 方案：

```sh
# /etc/systemd/system/opendesign-watch.service + .timer（每 15 分钟）
# 轮询 https://github.com/nexu-io/open-design/releases.atom（免鉴权、无限流）
# 发现新 tag → POST /repos/240xu/opendesign-linux/dispatches
#             {"event_type":"upstream-release","client_payload":{"tag":"open-design-v0.27.2"}}
```

`repository_dispatch` 收到 `client_payload.tag` 后会直接用它当 `upstream_ref`，
不再自己去猜版本号。

### 为什么 schedule 不是主通路

GitHub 官方文档明确两条：

1. 高负载时段 `schedule` 会延迟，**队列满时任务可能被丢弃**；
2. **public 仓库 60 天无活动后，scheduled workflow 会被自动禁用**，且只有提交一次
   改动 cron 的 commit 才会恢复。

所以 `cron: 17 */6 * * *` 只作兜底，主通路是外部 timer + `workflow_dispatch` /
`repository_dispatch`。

## 版本号从哪来（重要）

**上游 root `package.json` 的 `version` 不跟随 tag。** 实测：

| tag | root package.json | apps/packaged/package.json |
|---|---|---|
| `open-design-v0.27.2` | **0.25.1** | 0.27.2 ✅ |
| `open-design-v0.26.1` | **0.25.1** | 0.26.1 ✅ |

所以 workflow 优先从 tag 正则提取版本号，取不到才读 `apps/packaged/package.json`，
**绝不读 root**。读 root 会打出 `v0.25.1` 这种错 tag，且每 6 小时重复一次。

## Release 只在两种产物都成功时发布

`release` job 的条件是 `headless.result == 'success' && desktop.result == 'success'`。
任一失败则**不发 release**，避免出现「声称两种产物但缺件」。
