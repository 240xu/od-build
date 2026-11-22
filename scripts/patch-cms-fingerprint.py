#!/usr/bin/env python3
"""应用上游 PR #8538 的修复：CMS release fingerprint 改为探测工作区真实输入。

未修时 packaged web payload 会用 existsSync(WEB_ROOT/src/components/touchpoint-component.ts)
判定"有工作区源码"，然后去读 WORKSPACE_ROOT/apps/web/app/layout.tsx —— 打包布局下该文件
不存在 → ENOENT → next.config 加载失败 → web sidecar exit 1 → headless 起不来。
"""
import pathlib
import sys

f = pathlib.Path('apps/web/next.config.ts')
if not f.exists():
    sys.exit('apps/web/next.config.ts not found')

s = f.read_text()
if 'hasCmsHostReleaseInputs' in s:
    print('already patched (upstream merged it)')
    sys.exit(0)

anchor = 'export function cmsHostReleaseFingerprint('
helper = '''/**
 * Whether this checkout still carries the workspace sources the CMS host release
 * fingerprint reads. Packaged web payloads ship `apps/web` inside
 * `node_modules/@open-design/web`, so probing the package's own `src` reports
 * "present" for a tree with no workspace root (upstream PR #8538, fix #8536).
 */
export function hasCmsHostReleaseInputs(
  workspaceRoot: string,
  exists: (file: string) => boolean = existsSync,
): boolean {
  return CMS_HOST_RELEASE_INPUTS.every((file) => exists(resolve(workspaceRoot, file)));
}

'''
if s.count(anchor) != 1:
    sys.exit('anchor count = %d' % s.count(anchor))
s = s.replace(anchor, helper + anchor)

old = "NEXT_PUBLIC_CMS_HOST_RELEASE: existsSync(resolve(WEB_ROOT, 'src/components/touchpoint-component.ts'))"
new = 'NEXT_PUBLIC_CMS_HOST_RELEASE: hasCmsHostReleaseInputs(WORKSPACE_ROOT)'
if s.count(old) != 1:
    sys.exit('probe line count = %d' % s.count(old))
s = s.replace(old, new)

f.write_text(s)
print('patched apps/web/next.config.ts')
