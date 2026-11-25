#!/usr/bin/env python3
"""Suppress marketing surfaces that mount over the composer and the rail toggle.

WHY
  Upstream ships promo surfaces that render over functional UI:
    1. WhatsNewPopup           — post-update highlights dialog
    2. DeepSeekV4FlashCampaign — model promo modal

  Both mount a `.dialog_backdrop.modal-backdrop` layer with
  `pointer-events: auto`, so clicks land on the promo art instead of the input
  underneath. Measured on a 1400x900 window:
    composer centre (693,356) -> IMG.WhatsNewPopup-module__x4bVFa__cover
    rail toggle (25,5)        -> SECTION.InviteDialog-module___QsiSq__panel

  Upstream's own e2e helper (`e2e/lib/playwright/campaign-dismissals.ts`) solves
  exactly this by pre-seeding localStorage:
    "Marketing campaign modals must never interrupt functional UI specs ...
     stealing focus and burying the elements a spec is about to interact with."

  This applies the same idea at build time, so every bundle starts suppressed
  without touching nginx or the running deployment.

PATCHES  (anchor-matched, idempotent, non-fatal on anchor drift)
  1. `resolveWhatsNewPrompt` -> always 'none'
  2. `hasSeenCampaign`       -> always true

  A missing anchor prints SKIP with the observed count and lets the build pass:
  an upstream refactor then degrades to "promo shows again", never a broken build.
"""
from __future__ import annotations

import sys
from pathlib import Path

WHATS_NEW_ANCHOR = """export function resolveWhatsNewPrompt(
  info: Pick<WhatsNewResponse, 'id' | 'content'>,
  lastSeenId: string | null,
): WhatsNewPromptDecision {
  // No valid highlight to show (empty, unreachable, or malformed document).
  if (info.id == null || info.content == null) return 'none';
  // Already shown for this highlight.
  if (info.id === lastSeenId) return 'none';
  return 'show';
}"""

WHATS_NEW_REPLACEMENT = """export function resolveWhatsNewPrompt(
  info: Pick<WhatsNewResponse, 'id' | 'content'>,
  lastSeenId: string | null,
): WhatsNewPromptDecision {
  // PATCHED (patch-promo-suppress): the highlights dialog mounts a full-screen
  // `.dialog_backdrop.modal-backdrop` with `pointer-events: auto`, which buries
  // the composer on narrow windows until the visitor dismisses it. Suppress the
  // surface instead of requiring every visitor to close it first.
  void info;
  void lastSeenId;
  return 'none';
}"""

CAMPAIGN_ANCHOR = """function hasSeenCampaign(campaignId: string): boolean {
  if (typeof window === 'undefined') return true;
  try {
    return window.localStorage.getItem(`open-design:campaign-seen:${campaignId}`) === '1';
  } catch {
    // Fail closed: when the store is unreadable (private mode, disabled
    // localStorage) `markCampaignSeen` cannot persist either, so answering
    // "unseen" would re-open the modal on every mount. The campaign promise
    // is one appearance per window \u2014 suppress instead of spamming.
    return true;
  }
}"""

CAMPAIGN_REPLACEMENT = """function hasSeenCampaign(campaignId: string): boolean {
  // PATCHED (patch-promo-suppress): always report "seen". The campaign modal
  // opens over Home behind a pointer-events backdrop and swallows the composer
  // click for its whole window, so it is suppressed rather than pre-seeded.
  void campaignId;
  return true;
}"""

PATCHES = [
    ('apps/web/src/lib/whats-new.ts', WHATS_NEW_ANCHOR, WHATS_NEW_REPLACEMENT,
     'whats-new: never show the highlights dialog'),
    ('apps/web/src/components/DeepSeekV4FlashCampaign.tsx', CAMPAIGN_ANCHOR, CAMPAIGN_REPLACEMENT,
     'campaign: always report seen'),
]

MARKER = 'PATCHED (patch-promo-suppress)'


def apply(root: Path, dry_run: bool) -> int:
    skipped = 0
    for rel, anchor, replacement, label in PATCHES:
        target = root / rel
        if not target.is_file():
            print(f'  SKIP  {label} — {rel} missing (upstream layout changed)', file=sys.stderr)
            skipped += 1
            continue
        text = target.read_text(encoding='utf-8')
        if MARKER in text and anchor not in text:
            print(f'  OK    {label} — already patched')
            continue
        count = text.count(anchor)
        if count != 1:
            print(f'  SKIP  {label} — anchor count={count} (expected 1)', file=sys.stderr)
            skipped += 1
            continue
        if dry_run:
            print(f'  WOULD {label}')
            continue
        target.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
        print(f'  OK    {label}')
    return skipped


def main(argv: list[str]) -> int:
    dry_run = '--check' in argv
    args = [a for a in argv[1:] if not a.startswith('--')]
    root = Path(args[0]) if args else Path.cwd()
    print(f'patch-promo-suppress targeting {root} (dry_run={dry_run})')
    skipped = apply(root, dry_run)
    if skipped:
        print(f'  {skipped} patch(es) skipped — the affected promo may reappear; '
              'the build continues on purpose.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
