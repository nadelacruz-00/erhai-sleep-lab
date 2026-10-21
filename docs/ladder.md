# The ladder

Every rung must pass before the next one runs. Commands that change the
system need root; run them as `sudo ...` (in Claude Code: `! sudo ...`).

Wave 1a covers **step 2 and E0–E4.5**: nothing on this page puts the tablet
into a real sleep. Real-sleep rungs E5–E7 need the wave 1b classifier, beacon
and `ack`, and `erhai-lab probe` refuses them until then.

## Safety contract

- **Revert path:** a forced restart (hold power), then pick the **package
  kernel** in the rEFInd menu: the `.efi` whose `-b<N>` matches
  `dpkg-query -W oneplus-erhai-linux-7.3` (b28 on 2026-10-21; b27 also sits
  in `/boot` but runs with b28's modules, do not use it). `erhai-lab check`
  prints the mapping.
- **Hold the kernel package** for the campaign so the baseline cannot move:
  `sudo apt-mark hold oneplus-erhai-linux-7.3` (release with `unhold` at the end).
- A lab kernel only ever adds `/boot/<kver>-lab-<candidate>.efi` and
  `/usr/lib/modules/<kver>-lab-<candidate>/`. rEFInd's default never changes:
  every lab boot is a manual pick in the menu.
- The suspend override exists only while `erhai-lab probe` runs an attempt.
  Outside it, Suspend in the GNOME menu runs the dev's own harness unchanged.

## Install

    git clone https://github.com/nadelacruz-00/erhai-sleep-lab
    cd erhai-sleep-lab
    sudo tablet/install.sh
    sudo apt-mark hold oneplus-erhai-linux-7.3

`sudo tablet/install.sh uninstall` removes everything except the evidence in
`/var/lib/erhai-sleep/`.

## Step 2: dry runs on the package kernel (no sleep)

The dry run executes the real hook steps and their undo with everything awake;
it never writes `/sys/power/state`. Run each, and check the printed result.

| Run | Command | Pass |
|---|---|---|
| D1 backlight, Wi-Fi kept | `sudo erhai-lab dryrun` | screen off then back on, `restore errors none` |
| D2 GPU park + real blank | `sudo erhai-lab dryrun --display park` | GPU reaches `suspended`, screen blanks via the shell and returns, no restore errors |
| D3 Wi-Fi L1 | `sudo erhai-lab dryrun --wifi L1` | Wi-Fi drops to `unavailable`, `cnss_pci` unbinds and rebinds, Wi-Fi reconnects; dmesg signature shows **no** `erhai-cc`/`pwrseq` lines |
| D4 Wi-Fi L2 | `sudo erhai-lab dryrun --wifi L2` | exactly one pwrseq power-off on unbind and one clean `erhai-cc` bring-up on rebind, no SError/NoC lines, Wi-Fi reconnects |
| D5 guard | `sudo erhai-lab dryrun --wifi L1 --fail-at wifi-unbind-l1` | `ABORTED at pre-wifi-unbind-l1`, completed steps undone in reverse, no undo errors |
| D6 alarm readback | `sudo erhai-lab dryrun --alarm 30` | `alarm-arm` completes (readback within 3 s of the request) |

For D3–D5 the dry run turns the Wi-Fi radio off itself, stays down at least
30 s, and turns it back on at the end. Nothing is going to sleep, so
NetworkManager is not touching the chip at the same time. On a real attempt
NetworkManager turns the radio off by itself on PrepareForSleep, and the hook
never issues a second radio-off (D15).

**D4 can reset the SoC** (the WCN cold bring-up the dev saw fail). The dry run
syncs and journals before it starts, so a reset is attributable. After any
unexpected reset, check `mount | grep ' / '` is `rw` before going on.

## E0: evidence chain (lab kernel, no sleep)

1. Fetch and boot the debug kernel:

       sudo erhai-lab fetch 00-debug
       # reboot, pick 7.3.0-rc5-sm8750-themojoman-lab-00-debug in rEFInd

2. `sudo erhai-lab check`: every line `[ok]` except possibly `qcom_stats`.
3. pmsg survives a **long-press** reset (covers the A/C/D/E endings):

       echo "erhai-lab E0 marker $(date +%s)" | sudo tee /dev/pmsg0
       sync; echo s | sudo tee /proc/sysrq-trigger
       # hold power until the tablet resets, boot the lab kernel again
       sudo cat /sys/fs/pstore/pmsg-ramoops-0 2>/dev/null || sudo ls /var/lib/systemd/pstore/

   Pass: the marker line is there.
4. A kernel panic is recorded and reboots by itself (covers the B ending):

       sync; echo s | sudo tee /proc/sysrq-trigger
       echo c | sudo tee /proc/sysrq-trigger     # panics; reboots after 10 s
       # boot the lab kernel again
       sudo ls /sys/fs/pstore/ /var/lib/systemd/pstore/

   Pass: a `dmesg-ramoops-*` record with the `sysrq: Trigger a crash` panic.
5. After each reset: `mount | grep ' / '` shows `rw`.

Abort everything if step 3 or 4 finds nothing: without pstore, failures
cannot be attributed.

## E1–E4.5: pm_test rungs (lab kernel, no real sleep)

`pm_test` makes the kernel walk the suspend path up to a level and come back
after 5 s, CPUs never stopping. Each run prints a verdict and saves dmesg and
readouts under `/var/lib/erhai-sleep/<bootid>/<ts>/`.

| Rung | pm_test | Command | Pass |
|---|---|---|---|
| E1 | freezer | `sudo erhai-lab probe --rung E1` | verdict `pass` |
| E2 | devices | `sudo erhai-lab probe --rung E2 --wifi L1 --display park` (twice) | `pass` both times |
| E3 | devices | `sudo erhai-lab probe --rung E3 --display park` | `pass` |
| E4 | platform | `sudo erhai-lab probe --rung E4 --display park` | `pass`; read the saved dmesg for `erhai-cc`/`pwrseq` lines: their presence means the host power-off path (b) runs |
| E4u | platform | if E4 fails: `--wifi L1`, then `--wifi L2` | first level that passes |
| E4.5 | platform | `sudo erhai-lab probe --rung E4.5 --display park --alarm 30` | `pass` = the RTC alarm IRQ fired |

What each level exercises (from `kernel/power/suspend.c`):

- `freezer`: tasks frozen and thawed only.
- `devices`: every driver's `.suspend`/`.resume`; **no** late/noirq phase.
- `platform`: adds the late and noirq phases. This is the first rung that runs
  `qcom_pcie_suspend_noirq`/`resume_noirq` and the cnss2 noirq callbacks.

`--display park` (GPU park + real blank) is the default for every rung from E2
up. The dev measured a 3/6 silent reset at suspend entry when the display is
torn down under an awake GPU (D13), so backlight-only (`--display backlight`)
is only a comparison run.

## Global abort rules

- Any silent reset (no panic in pstore): stop climbing and note the rung.
- Root comes back read-only or fsck finds errors: stop, back up, find the
  cause before continuing.
- Two unexplained failures on one rung: stop.
- Never a real sleep without a confirmed alarm armed as the hook's last step
  (wave 1b).

## Failure classes (the wave 1b classifier files every attempt as one)

| Class | Meaning |
|---|---|
| pass | resumed, screen confirmed by `ack screen=yes` |
| D | resumed (journal `resume-ok`), screen dark |
| reboot-hung | resumed, the beacon reboot did not complete |
| B | no `resume-ok`; pstore holds a DPM-watchdog panic or an oops naming a device |
| C | no `resume-ok`, no panic; silent reset during resume |
| E | no `resume-ok`, no panic; silent reset during suspend entry (last console line before the s2idle loop) |
| A | no `resume-ok`, no panic; ended by the user's long press (wake never arrived) |
| abort | the attempt never entered sleep (guard fired or `suspend_stats.fail` moved) |
