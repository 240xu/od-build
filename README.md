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
