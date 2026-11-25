# 促销弹窗抑制：官方途径与本仓库实践

本仓库构建的 OpenDesign Linux headless bundle，会在首页遇到三类「促销/提示」表面。
它们都挂 `pointer-events: auto` 的全屏遮罩（`.dialog_backdrop.modal-backdrop`），
在窄窗口下会把 composer 输入框和左上角侧栏按钮整个盖住 —— 点不到。

本文记录：

1. 三个弹窗各自的机制（附上游源码位置）
2. **上游官方提供的抑制途径**（这是唯一被官方文档承认的路径）
3. 我们的 packaged 部署为什么需要一处补丁
4. 两种落地方法的对比

---

## 一、三个弹窗及其机制

### ① WhatsNew 更新卡

界面文字：`OpenDesign 0.27.1 — Invite Friends, Earn Reset`

| 项 | 值 |
|---|---|
| 上游源码 | `apps/web/src/lib/whats-new.ts`（`resolveWhatsNewPrompt`） |
| 触发条件 | `/api/whats-new` 返回的 `id` ≠ localStorage `od-whats-new-last-seen-id` |
| 当前 id | `0.27.1`（服务端控制，来自 `whatsnew.open-design.ai/whats-new.json`） |
| 形态 | 全屏遮罩，`z-index: 1500`，`rgba(255,255,255,0.6)` |
| 实测遮挡 | composer 中心点 `(693,356)` 命中 `IMG.WhatsNewPopup-module__x4bVFa__cover` |

**官方设计意图**（源码注释原文）：

> "A fresh profile that has never seen the current `id` shows the card once —
> the document is deliberately curated, so surfacing the current highlight
> to a new user once is intended."

即：**新浏览器第一次必须弹一次，这是有意的设计。**

### ② DeepSeek 模型促销

| 项 | 值 |
|---|---|
| 上游源码 | `apps/web/src/components/DeepSeekV4FlashCampaign.tsx`（`hasSeenCampaign`） |
| 触发条件 | localStorage `open-design:campaign-seen:<campaignId>` ≠ `'1'` |
| campaignId | `deepseek-v4-dual-unlimited-2026` / `deepseek-v4-flash-unlimited-2026` |
| 形态 | 同款全屏遮罩 |

**官方 e2e 注释承认它会挡测试**：

> "Marketing campaign modals must never interrupt functional UI specs ...
> stealing focus and burying the elements a spec is about to interact with."

### ③ Invite 邀请横幅

界面文字：`Invite colleagues for free. Design together.`

| 项 | 值 |
|---|---|
| 上游源码 | `apps/web/src/components/HomeInviteSurface.tsx` |
| 触发条件 | 已登录 + `memberStatus === 'active'` + `lifecycleState === 'active'` + `permissions.canInviteMembers` + 未写过 dismissed key |
| localStorage key | `od.invitation-banner.dismissed:<accountId>`（未登录时 `:local`） |
| 实测遮挡 | 侧栏 toggle `(25,5)` 命中 `SECTION.InviteDialog-module___QsiSq__panel` |

**关键难点**：key 内含 `accountId`，它在 React state 里，构建期和注入期都无法预知。

---

## 二、上游官方提供的抑制途径

以下全部出自上游文档 / 代码，**不是我们的发明**。

### 途径 ①：源头法（发布 `{}`）

`docs/whats-new.md` 原文：

> "To retire the card entirely, publish an empty object (`{}`); the daemon then
> resolves to 'no highlight'. Any *other* incomplete document also resolves to
> 'no highlight', but that is the accident case, not the intended one."

**可行性**：❌ 该文档托管在上游 Cloudflare R2（`whatsnew.open-design.ai`），
自建部署无法修改。

### 途径 ②：覆盖法（`OD_WHATS_NEW_URL`）

`docs/whats-new.md:35` 与 `tools/pack/AGENTS.md:68` 原文：

> "`OD_WHATS_NEW_URL` overrides the source for local development and tests
> (for example a `tools-serve` fixture endpoint), and opts any channel in."

**实现**（`apps/daemon/dist/services/whats-new.js`）：

```js
export function whatsNewSourceUrl(env, channel) {
    const override = env.OD_WHATS_NEW_URL?.trim();
    if (override) return override;
    return WHATS_NEW_RELEASE_CHANNELS.has(channel) ? DEFAULT_WHATS_NEW_URL : null;
}
```

**可行性**：⚠️ 机制成立，实测有效 —— 但见第三节的部署限制。

### 途径 ③：channel 法（让构建不落在 release channel）

同一份代码：

```js
const WHATS_NEW_RELEASE_CHANNELS = new Set(['beta', 'prerelease', 'preview', 'stable']);
// sourceUrl == null → return { id: null, content: null } —— 一个网络请求都不发
```

channel 来源（`apps/daemon/dist/app-version.js:98`）：

```js
const channel = cleanString(env.OD_RELEASE_CHANNEL)
    ?? cleanString(env.OD_APP_CHANNEL)
    ?? inferredChannel                       // 从 version 字符串推断
    ?? (packaged ? 'stable' : 'development');
```

**可行性**：⚠️ `OD_RELEASE_CHANNEL` / `OD_APP_CHANNEL` 同样不在 packaged 白名单；
且 `version = 0.27.2` 会被推断成 `stable`。

---

## 三、packaged 部署的限制（决定性）

上游的 `tools-pack` 打包器在启动 sidecar 前会过滤环境变量
（`apps/packaged/dist/headless.mjs`）：

```js
var PACKAGED_CHILD_ENV_ALLOWLIST = [
  "CODEX_HOME", "HOME", "HTTP_PROXY", "HTTPS_PROXY", "LANG", "LC_ALL",
  "LOGNAME", "ALL_PROXY", "NODE_USE_ENV_PROXY", "NO_PROXY", "TMPDIR", "USER",
  "VP_HOME", "all_proxy", "http_proxy", "https_proxy", "no_proxy",
  "OD_ALLOWED_INTERNAL_HOSTS", "OD_JSON_IPC_TRACE", "OD_TELEMETRY_ENV"
];                                                     // ← 20 项，共 20 个
function shouldForwardPackagedChildEnv(key, includeProviderSecrets = false) {
  return PACKAGED_CHILD_ENV_ALLOWLIST.includes(key)
      || includeProviderSecrets && (key.endsWith("_API_KEY") || key.endsWith("_TOKEN"));
}
```

**这意味着**：

| 变量 | 官方文档承诺 | packaged 是否转发 |
|---|---|---|
| `OD_WHATS_NEW_URL` | ✅ 明写可用 | ❌ **不在白名单** |
| `OD_RELEASE_CHANNEL` | ✅ 代码支持 | ❌ 不在白名单 |
| `OD_APP_CHANNEL` | ✅ 代码支持 | ❌ 不在白名单 |
| `OD_ALLOWED_ORIGINS` | ✅ 代码支持 | ❌ 不在白名单（2026-11-22 已单独踩过） |

**实测证据**（在 `/srv/od-test` 的隔离实例上）：

```
不补白名单 → daemon 的 /proc/<pid>/environ 里 grep OD_WHATS_NEW_URL = 0 条
补白名单一行 → daemon 拿到 OD_WHATS_NEW_URL
             → GET /api/whats-new 返回 {"version":"0.25.1","id":null,"content":null}
```

**结论**：在我们这套 packaged headless 部署上，
**「纯官方、零补丁」地抑制 WhatsNew 更新卡 = 不可行**。

---

## 四、两种落地方法对比

### 方法 A：白名单补丁 + `OD_WHATS_NEW_URL`（官方机制 + 一处管道补丁）

**改动**：

1. `packaged/dist/headless.mjs` 的 `PACKAGED_CHILD_ENV_ALLOWLIST` 加一行 `"OD_WHATS_NEW_URL"`
2. 起一个返回 `{}` 的本地 HTTP 服务（官方文档里 `OD_WHATS_NEW_URL` 就是给 fixture 用的）
3. launcher 里设 `OD_WHATS_NEW_URL=http://127.0.0.1:<port>/whats-new.json`
4. 重启

**效果**：

```
GET /api/whats-new → {"version":"0.25.1","id":null,"content":null}
→ resolveWhatsNewPrompt 判定 'none' → 更新卡不弹
```

**纯度**：官方机制 + 1 行管道补丁（不碰任何业务函数）
**覆盖**：仅 WhatsNew（弹窗 ②③ 无效）
**维护**：每次上游升级需重打白名单一行（幂等脚本化）

### 方法 B：源码级强制抑制

**改动**：改 `resolveWhatsNewPrompt` 与 `hasSeenCampaign` 的返回值。

**纯度**：❌ 改了业务逻辑，偏离官方（**本仓库已撤回，见 commit `2ef28b9`**）
**覆盖**：WhatsNew + campaign 都不弹（Invite 仍无效）
**维护**：每次升级要重打两处（锚点可能漂移）

---

## 五、结论

| 诉求 | 可行方案 |
|---|---|
| 要「纯官方、零补丁」 | ❌ **做不到**。packaged 白名单是硬阻塞 |
| 要「官方机制 + 最小补丁」 | ✅ 方法 A（1 行白名单 + 1 个本地 fixture） |
| 要「彻底不弹」 | 方法 B（已撤回，因为偏离官方） |
| Invite 弹窗 | **任何自动方案都无效**（key 需要 accountId）；只能在浏览器里手动点一次 `Skip for now` |

**当前仓库状态**：方法 B 已完全撤回（`commit 2ef28b9`），CI 不含任何源码补丁。
方法 A 仅在隔离实例 `/srv/od-test` 上验证过，**尚未上生产**。

---

## 附：上游可反馈的问题

`OD_WHATS_NEW_URL` 在文档中明确承诺可用，但 `PACKAGED_CHILD_ENV_ALLOWLIST`
（`apps/packaged/dist/headless.mjs:1006` 起）未收录该键。
同类问题已出现两次（`OD_ALLOWED_ORIGINS`、`OD_WHATS_NEW_URL`），
建议上游在 `PACKAGED_CHILD_ENV_ALLOWLIST` 中补入文档提及的所有 `OD_*` 覆盖变量。
