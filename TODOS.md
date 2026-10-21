# TODOS

## Sleep lab

### Pad 2 Pro oracle kernel as a CI candidate

**What:** Add candidate `30-oracle-pad2pro`: a CI job building `yzddmr6/linux-sm8750-erhai` (branch `erhai/v0.2`, v7.2 base, ath12k) as a third UKI, with its own config fragment.

**Why:** A verified-working s2idle kernel on identical hardware allows differential debugging (DT, config, Wi-Fi stack) instead of reasoning from first principles about cnss2.

**Context:** Deferred by eng review D3 (2026-10-21). Use only if the E-ladder is ambiguous after E7. That kernel may not fully boot this Ubuntu userspace (different Wi-Fi/BT stack, display pipeline); as a sleep oracle it only needs a shell. Start from the design doc's candidate description and `kernel/source.json` of the Pad 2 Pro port.

**Effort:** M
**Priority:** P3
**Depends on:** E7 results in the ledger

### Package the tablet kit as a `.deb`

**What:** `erhai-sleep-lab` Debian package: the `erhai-lab` tool, the `system-sleep` caller, `erhai-sleep-boot.service`, the drop-in writers, with postinst/postrm equal to `install.sh`/`uninstall`.

**Why:** One-command install for other Pad 3 owners and a form the port's maintainer can adopt.

**Context:** Deferred by eng review D11 (2026-10-21). Wave 1 ships plain files + `install.sh`. Package only once the hook contract is stable (after E5 passes). Mirror the dev's `oneplus-erhai-*` package layout; PRs are gated by D5 (user confirmation).

**Effort:** S
**Priority:** P3
**Depends on:** E5 pass; D5 PR gate

### pstore ftrace region for silent-reset attribution

**What:** DT patch adding `ftrace-size = <0x40000>` to `reserved-memory/ramoops@a7800000` (inside the existing 2 MiB region) plus an opt-in probe flag that writes `1` to `/sys/kernel/debug/pstore/record_ftrace` for one attempt.

**Why:** A class C/E silent reset leaves no console line; the last few hundred traced kernel functions name the path that was executing.

**Context:** Deferred by eng review D12 (2026-10-21). `CONFIG_PSTORE_FTRACE=y` is already in candidate `00-debug` but records nothing without the region. Do this only after a class C or E result appears in the ledger; function tracing adds overhead to every attempt.

**Effort:** S
**Priority:** P3
**Depends on:** a class C or E result in the ledger

## Completed
