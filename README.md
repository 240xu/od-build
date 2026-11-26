# OpenDesign for Linux

Prebuilt Linux artifacts for [nexu-io/open-design](https://github.com/nexu-io/open-design),
produced by GitHub Actions from **unmodified upstream source**.

Upstream publishes no Linux binaries — 40 releases, 228 assets, zero Linux
files. This repository fills that gap with two artifacts per release.

| Asset | Contents | Use |
|---|---|---|
| `od-headless-stable.tar.gz` | daemon + web sidecar, **no Electron** | Self-hosted server behind nginx |
| `Open.Design-stable.AppImage` | full desktop build | Local desktop app |

---

## Install headless

```sh
tar -xzf od-headless-stable.tar.gz
cd <extracted-dir>
./launcher/open-design-headless-stable --headless
```

The launcher prints the web URL and exits; the sidecar supervisor it spawned is
reparented to init, so the process tree survives. Run it under a supervisor
(systemd `Restart=always`, or a keep-alive wrapper) — a bare foreground launch
dies with your shell.

Minimal systemd unit:

```ini
[Unit]
Description=OpenDesign headless
After=network-online.target

[Service]
Type=simple
User=od
WorkingDirectory=/opt/open-design
ExecStart=/bin/bash /opt/open-design/bin/start.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`start.sh` is your keep-alive wrapper around the launcher: wait for the sidecar
to report ready, then poll it and exit on failure so systemd restarts the whole
tree.

### Required nginx workarounds

**The bundle does not work behind a reverse proxy without two nginx-side fixes.**
Both are proxy-layer only; neither touches the source tree.

```nginx
location / {
    include /etc/nginx/snippets/od-headless.conf;   # ← the two fixes
    proxy_pass http://127.0.0.1:7457;
    proxy_request_buffering off;
    proxy_buffering off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```

Grab the snippet from [`examples/nginx/od-headless.conf`](examples/nginx/od-headless.conf).

| Fix | What breaks without it |
|---|---|
| `proxy_set_header Origin ""` | Every write returns 403 — cannot create a project or send a message |
| `Accept-Encoding ""` + `gzip off` + `sub_filter` | Sidebar toggle is dead below 1080px |

Full analysis, evidence, and the upgrade verification checklist:
[`docs/UPSTREAM-LIMITATIONS.md`](docs/UPSTREAM-LIMITATIONS.md).

> These fixes disable the daemon's own origin check. Put authentication in
> nginx before the proxy — a token or cookie gate, not an open proxy.

---

## Install desktop

```sh
chmod +x Open.Design-stable.AppImage
./Open.Design-stable.AppImage
```

`chmod +x` is required: artifact transfer does not preserve the executable bit.

> GitHub sanitises spaces in asset names — `Open Design-stable.AppImage`
> becomes **`Open.Design-stable.AppImage`**.

---

## Which upstream ref gets built

**With `upstream_ref` empty, only the latest upstream release tag is built.
The workflow never falls back to `main`.**

Upstream `main` and release tags diverge — at `v0.27.2`, `main` was 24 commits
ahead and the tag 13 ahead. A build that silently fell back to `main` produced a
release labelled `v0.27.2` whose contents were newer than that tag — version and
content could not be reconciled when debugging.

To build `main`, pass it explicitly:

```sh
gh workflow run build-linux.yml -f upstream_ref=main
```

The resulting tag carries a `-main.<sha7>` suffix (e.g. `v0.27.3-main.a1b2c3d`)
so provenance stays visible.

---

## Triggering a build

| How | Command |
|---|---|
| Auto (upstream release) | External watcher polls `releases.atom`, POSTs a `repository_dispatch` |
| Auto (fallback) | `schedule`, `cron: 17 */6 * * *` (UTC) |
| Manual | `gh workflow run build-linux.yml [-f upstream_ref=<ref>] [-f force=true]` |

Duplicate builds of the same version are skipped. `force=true` overrides that —
use it to repair a damaged release.

> GitHub's own `schedule` is best-effort: runs can be dropped under load, and a
> public repo's schedule is disabled after 60 days without activity (restoring
> it requires a commit that changes the cron line). The external watcher is the
> primary path; `schedule` is the fallback.

---

## How the build works

```
resolve upstream ref + version
   ↓
pnpm install (pinned 10.33.2) → build web static export
   ↓
patch next.config (upstream PR #8538 — CMS fingerprint)
   ↓
assemble payload → verify prerequisites → generate launcher → package
   ↓
smoke-run the launcher (must exit 0)
   ↓  (headless and desktop both)
create/update release, tag pinned to the build commit
```

Build-only settings that do not exist in the upstream CI:

| Setting | Why |
|---|---|
| `ONNXRUNTIME_NODE_INSTALL_CUDA=skip` | Avoids a 404 on the optional CUDA download |
| pnpm `10.33.2` | The root `engines` field rejects newer pnpm outright |
| `containerized=false` | `--containerized` is currently broken upstream: `buildDockerArgs` does not pass `CI`, so the container has no TTY and pnpm aborts with `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY` |

The AppImage is validated before release: ELF magic, `--appimage-extract` succeeds,
`AppRun` is executable, and the bundled node plus resources are present. A
truncated or incomplete file fails the build.

---

## Repository layout

```
.github/workflows/build-linux.yml   the whole pipeline
scripts/patch-cms-fingerprint.py    idempotent patch for upstream PR #8538
scripts/make-launcher.py            launcher generator (symlink-resolving)
scripts/make-readme.py              bundle README generator
scripts/smoke-headless.py           post-package smoke run
examples/nginx/od-headless.conf     the two required proxy fixes
docs/UPSTREAM-LIMITATIONS.md        why those fixes exist, with evidence
docs/PROMO-SUPPRESSION.md           marketing surfaces, and why they are untouched
```

Authentication, fail2ban, nginx injection, and tokens all live on the deployment
host and are **not** in this repository.

---

## Upgrading

Replace the bundle directory with the new artifact, keep your data directory, and
re-apply the nginx snippet. If you patched `PACKAGED_CHILD_ENV_ALLOWLIST` instead
of using the proxy workaround, re-apply that patch — a fresh bundle does not
carry it.

Verify with the checklist in
[`docs/UPSTREAM-LIMITATIONS.md`](docs/UPSTREAM-LIMITATIONS.md#verification-checklist-run-after-every-upgrade).

---

## Licence

Artifacts contain upstream code; upstream licensing applies. This repository
holds only the build harness.
