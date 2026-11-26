# Upstream limitations and the two proxy-side workarounds

The Linux bundle in this repository is built from unmodified upstream source.
It is, however, unusable behind a reverse proxy without two nginx-side
workarounds. Both stem from upstream behaviour that cannot be fixed from the
build side without diverging from the official tree.

This document records the evidence, the exact fix, and the trade-offs, so the
workarounds can be re-verified after every upstream upgrade.

Ready-to-include snippet: [`examples/nginx/od-headless.conf`](../examples/nginx/od-headless.conf).

---

## Fix 1 — blank `Origin`, or every write request returns 403

### Symptom

A browser opening the deployment cannot create a project or send a message.
The UI reports *"could not create project"*. The daemon logs 403 on
`POST /api/projects` and on `POST /api/runs`.

### Cause: `PACKAGED_CHILD_ENV_ALLOWLIST` omits `OD_ALLOWED_ORIGINS`

`apps/packaged/dist/headless.mjs` filters the environment before spawning the
daemon:

```js
var PACKAGED_CHILD_ENV_ALLOWLIST = [
  "CODEX_HOME", "HOME", "HTTP_PROXY", "HTTPS_PROXY", "LANG", "LC_ALL",
  "LOGNAME", "ALL_PROXY", "NODE_USE_ENV_PROXY", "NO_PROXY", "TMPDIR", "USER",
  "VP_HOME", "all_proxy", "http_proxy", "https_proxy", "no_proxy",
  "OD_ALLOWED_INTERNAL_HOSTS", "OD_JSON_IPC_TRACE", "OD_TELEMETRY_ENV"
];

function shouldForwardPackagedChildEnv(key, includeProviderSecrets = false) {
  return PACKAGED_CHILD_ENV_ALLOWLIST.includes(key)
      || includeProviderSecrets && (key.endsWith("_API_KEY") || key.endsWith("_TOKEN"));
}
```

Twenty entries, none of them `OD_ALLOWED_ORIGINS`. Verified on a live
deployment: setting `OD_ALLOWED_ORIGINS` in the launcher leaves the daemon
environment untouched — `grep OD_ALLOWED_ORIGINS /proc/<daemon>/environ` returns
zero matches.

Without the variable, the daemon falls back to rejecting any request that
carries an `Origin` header. Because the browser sends `Origin` even for
same-origin `POST`, every write fails.

### Fix

Strip the header in nginx — the proxy already authenticated the request:

```nginx
proxy_set_header Origin "";
```

### Trade-off

The daemon's own origin check is effectively disabled; the security boundary
moves entirely to nginx. That is acceptable only if the proxy really does
authenticate. This repository's reference deployment gates every request on a
token or cookie before proxying.

### Permanent alternative

Add `"OD_ALLOWED_ORIGINS"` to `PACKAGED_CHILD_ENV_ALLOWLIST`, rebuild, and
re-apply on every upgrade. This diverges from the official packaged tree by one
line, and forgetting it on upgrade brings the 403s straight back. The proxy
workaround has no such recurring cost.

---

## Fix 2 — the sidebar toggle does nothing below 1080px

### Symptom

Narrow the window below 1080px and the top-left sidebar button stops working.
Its `aria-expanded` flips, but no menu appears, so Projects, Design systems,
Plugins and Settings are unreachable.

### Cause: upstream zeroes the docked rail and never builds the narrow fallback

`apps/web/src/styles/home/entry-layout.css`:

```css
@media (max-width:1080px){
  .entry-shell--no-header .entry.entry--rail-open{
    grid-template-columns: 0 minmax(0,1fr);   /* rail track → 0 */
  }
  .entry--rail-open .entry-nav-rail{
    pointer-events: none;                    /* rail → not clickable */
    overflow: hidden;                        /* rail → clipped */
  }
}
```

The docked default is `--entry-rail-width: 236px`
(`.entry-shell--no-header{--entry-rail-width:236px}`). Below the breakpoint the
toggle keeps flipping the persisted docked state, which can never render at
that width.

The upstream comment on `railOpen` describes the intended behaviour — "opens it
as an overlay that dismisses on selection / backdrop click / Escape" — but that
overlay was never implemented. The real fix is upstream PR
**#9306** (`fix(web): open the entry rail as an overlay drawer on narrow
windows`), which as of 2026-11-26 is still open and not merged into `main` or
any release tag.

### Fix

Re-assert the track width and pointer events below 1080px:

```nginx
proxy_set_header Accept-Encoding "";
gzip off;
sub_filter_once on;
sub_filter_types text/html;
sub_filter '</head>' '<style id="od-rail-fix">@media (max-width:1080px){.entry-shell--no-header .entry.entry--rail-open{grid-template-columns:var(--entry-rail-width,236px) minmax(0,1fr)!important}.entry--rail-open .entry-nav-rail{pointer-events:auto!important;overflow:visible!important}}</style></head>';
```

### The two non-obvious parts

**`Accept-Encoding ""` and `gzip off` are mandatory.** `sub_filter` rewrites
plain text only. Next.js serves gzipped HTML to any browser that advertises
gzip, so with compression left on the filter silently matches nothing and the
patch looks applied in `curl` while being absent in the browser. This failure
mode was hit once already; the fix is to disable compression for that response.

**`236px`, not `56px`.** `56px` is a value borrowed from a different layout
system; the upstream rail track here is 236px. `var(--entry-rail-width, 236px)`
uses the live value when defined and falls back correctly if upstream ever
removes it.

### When this becomes unnecessary

Once upstream merges PR #9306, the overlay drawer handles narrow windows itself
and the injection can be deleted. Re-check `entry-layout.css` for
`entry--rail-overlay` on each upgrade.

---

## Verification checklist (run after every upgrade)

```bash
# 1. Origin stripping present and write path works
curl -sS -X POST -H 'Content-Type: application/json' \
  -d '{"id":"probe","name":"probe"}' http://127.0.0.1:7457/api/projects
# expect 200 with a project object

# 2. Rail fix reaches the browser, not just curl
curl -sS -H 'Accept-Encoding: gzip, deflate, br' https://<host>/ | grep -c 'od-rail-fix'
# expect 1

# 3. Upstream has not shipped its own narrow-window fix
#    (if it has, drop Fix 2 — see "When this becomes unnecessary")
grep -c 'entry--rail-overlay' \
  out/linux/namespaces/*/assembled/app/node_modules/@open-design/web/out/_next/static/chunks/*.css
# expect 0

# 4. Both fixes survive a config reload
nginx -t && systemctl reload nginx
```

---

## What is deliberately NOT patched here

Three marketing surfaces mount over functional UI and can obscure the composer
and the rail toggle:

| Surface | Trigger | Upstream position |
|---|---|---|
| WhatsNew update card | `/api/whats-new` id ≠ `od-whats-new-last-seen-id` | `apps/web/src/lib/whats-new.ts` |
| DeepSeek campaign modal | `open-design:campaign-seen:<id>` ≠ `'1'` | `apps/web/src/components/DeepSeekV4FlashCampaign.tsx` |
| Invite banner | logged in + `canInviteMembers` + not dismissed | `apps/web/src/components/HomeInviteSurface.tsx` |

Upstream documents one official way to retire the WhatsNew card: publish an
empty object (`{}`) to the highlights document, or point `OD_WHATS_NEW_URL` at
your own copy (`docs/whats-new.md`). **These are not applied in this bundle.**

- Publishing `{}` requires control of `whatsnew.open-design.ai`, which a
  self-hosted deployment does not have.
- `OD_WHATS_NEW_URL` is documented but **also missing from
  `PACKAGED_CHILD_ENV_ALLOWLIST`** — the same defect as Fix 1. Making it work
  requires the same one-line allowlist patch, so it is not a zero-patch path
  either.

The reference deployment therefore ships **unmodified upstream behaviour** for
all three surfaces. They appear once per browser and are dismissed with one
click each; both the update card and the campaign modal remember the dismissal
in `localStorage`, and the invite banner remembers it per account.

A source-level suppression was prototyped and reverted (`commit 2ef28b9`). It
worked, but changing the shipped behaviour of a marketing surface is a product
decision, not a packaging one, and it diverges from the official tree on every
upgrade.

---

## Reporting these upstream

Both defects are the same shape: **a documented `OD_*` override that
`PACKAGED_CHILD_ENV_ALLOWLIST` does not forward.**

- `OD_ALLOWED_ORIGINS` — documented, forwarded: no → every proxied deployment
  hits 403 on writes
- `OD_WHATS_NEW_URL` — documented, forwarded: no → the sanctioned way to
  retire the update card does not work in packaged builds

A single upstream change fixes both: forward every `OD_*` variable the daemon
documents reading, or at minimum add these two entries to the allowlist.
