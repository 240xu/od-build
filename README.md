# od-build

在 GitHub Actions 上构建 [OpenDesign](https://github.com/nexu-io/open-design) 的 Linux 产物。

## 为什么需要这个

官方 Linux 只有 Docker 路径，**不发布 AppImage / headless 预构建包**
（穷举 40 个 release 共 228 个 asset，零 linux 资产）。

本地构建踩到两个坑：

1. `onnxruntime-node` 的 install 钩子去下载 CUDA EP 二进制，受限网络下 404 → 构建失败。
   解法：`ONNXRUNTIME_NODE_INSTALL_CUDA=skip`（官方脚本支持的开关）。
2. 本地 pnpm 11.28.5 被 `engines.pnpm >=10.33.2 <11` 硬拒。
   解法：CI 里 pin 10.33.2。

GitHub runner 网络干净、pnpm 版本可控，这两个坑都不存在。

## 怎么用

Actions → **Build OpenDesign Linux** → Run workflow

| 输入 | 说明 |
|---|---|
| `upstream_ref` | 上游分支/tag/commit，默认 `main` |
| `target` | `appimage`（桌面版）或 `dir`（解包目录） |
| `containerized` | 在 `electronuserland/builder` 镜像内构建，glibc 2.27 基线，兼容更老的发行版 |

产物在 run 页面的 Artifacts 里：

- `Open Design-stable.AppImage` — 桌面版
- `od-headless-stable.tar.gz` — headless 运行集（assembled + resources）

## 两个必须注意的点

1. **web 静态导出必须单独构建。**
   `apps/web/package.json` 的 `files` 不含 `out`，`pnpm pack` 不会带上它，
   而 headless 的 web sidecar 走 Next 静态导出。workflow 里先 `pnpm --filter @open-design/web build`
   再 `cp -a apps/web/out` 进 assembled。

2. **onnxruntime 必须 skip CUDA。**
   否则 `npm install` 阶段直接失败。见 workflow 顶部 `env`。

## 参考

- 官方 Linux 安装文档：`docs/install-guide.md`（Docker 为唯一支持路径）
- 官方打包工具：`tools/pack/README.md`（`linux build/install/start --headless`）
- 官方 CI 里 `build_linux` 任务被 `vars.ENABLE_STABLE_LINUX` 禁用，注释写明
  「Linux AppImage packaging is temporarily excluded from stable releases」
