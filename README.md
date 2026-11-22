# od-build

在 GitHub Actions 上构建 [OpenDesign](https://github.com/nexu-io/open-design) 的 **Linux headless 运行集**。

## 为什么

官方 Linux 只有 Docker 路径，**不发布任何 AppImage / deb / headless 预构建包**
（穷举 40 个 release 共 228 个 asset，零 linux 资产）。

本仓库只产出 **纯 headless**（daemon + web，**不含 Electron**），用于 CLI + 浏览器场景。

## 用法

Actions → **Build OpenDesign headless (Linux, no Electron)** → Run workflow

| 输入 | 说明 |
|---|---|
| `upstream_ref` | 上游分支/tag/commit，默认 `main` |
| `namespace` | 产物目录名与 launcher stamp，默认 `stable` |

产物：`od-headless-<namespace>.tar.gz`

## 产物结构（与官方 launcher 目录契约一致）

```
out/linux/namespaces/<ns>/assembled/    应用主体（已补 web/out 静态导出）
out/linux/namespaces/<ns>/resources/    bundled node + vela
runtime/linux/                           运行期数据
launcher/open-design-headless-<ns>       启动脚本
```

## 构建期已知坑（都已在本 workflow 里处理）

1. **`--containerized` 当前不可用。** 官方 `buildDockerArgs` 不把 `CI` 传进容器，
   容器内无 TTY → `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY` → docker build exit 1。
   官方自己也在 workflow 注释里写「等 containerized pnpm bootstrap 修好再启用 Linux lane」。
   → 走非 containerized 原生构建。

2. **`onnxruntime-node` 的 install 钩子会下 CUDA EP 二进制**，受限网络下 404。
   → `ONNXRUNTIME_NODE_INSTALL_CUDA=skip`。

3. **`apps/web/package.json` 的 `files` 不含 `out`**，`pnpm pack` 不会带上，
   而 headless 的 web sidecar 走 Next 静态导出。
   → 先 `pnpm --filter @open-design/web build`，打包后 `cp -a apps/web/out` 进 assembled。

4. **上游 main 缺 PR #8538。** `apps/web/next.config.ts` 的 CMS fingerprint 探测写的是
   web 包自己的 `src`，打包后恒为「存在」→ 去读 `WORKSPACE_ROOT/apps/web/app/layout.tsx`
   → ENOENT → next.config 加载失败 → web sidecar exit 1。
   → `scripts/patch-cms-fingerprint.py` 幂等打补丁（上游合并后自动跳过）。

5. **`tools-pack --dir` 的输出多一层 `out/`。** 实际路径是
   `<dir>/out/linux/namespaces/<ns>/...`，不是 `<dir>/linux/namespaces/...`。

6. **launcher 的 ROOT 只上一级**（launcher 在 `<root>/launcher/` 下）。

## 部署

```sh
tar -xzf od-headless-stable.tar.gz -C ~/od-stable
~/od-stable/launcher/open-design-headless-stable
```

启动后 daemon/web 监听 `127.0.0.1` 动态端口，用官方 status IPC 查实际 URL。
数据落在 `runtime/linux`。

**保活注意**：官方 headless 主进程打印 URL 后会主动 return（supervisor 被 reparent 到
init），所以 systemd 直接用 `Type=simple` 跑 launcher 会看到「主进程正常退出」并连带
SIGKILL 整棵 cgroup。需要包装脚本盯住 sidecar 状态 IPC 维持存活。

## 本仓库不含任何部署侧配置

认证门、fail2ban、nginx 注入、token 等全部留在部署主机，不进此仓库。
