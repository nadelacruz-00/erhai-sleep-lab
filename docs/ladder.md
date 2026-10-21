# The ladder

Every rung must pass before the next one runs. Commands that change the
system need root; run them as `sudo ...` (in Claude Code: `! sudo ...`).

Wave 1a covers **step 2 and E0–E4.5**: nothing on this page puts the tablet
into a real sleep. Real-sleep rungs E5–E7 need the wave 1b classifier, beacon
and `ack`, and `erhai-lab probe` refuses them until then.

## Safety contract

- **Revert path:** a forced restart (hold **power + volume up**; power alone does not reset this tablet), then pick the **package
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
| ~~D3 Wi-Fi L1~~ **suspended** (see below) | `sudo erhai-lab dryrun --wifi L1` | Wi-Fi drops to `unavailable`, `cnss_pci` unbinds and rebinds, Wi-Fi reconnects; dmesg signature shows **no** `erhai-cc`/`pwrseq` lines |
| D4 Wi-Fi L2 | `sudo erhai-lab dryrun --wifi L2` | exactly one pwrseq power-off on unbind and one clean `erhai-cc` bring-up on rebind, no SError/NoC lines, Wi-Fi reconnects |
| D5 guard | `sudo erhai-lab dryrun --wifi L1 --fail-at wifi-unbind-l1` | `ABORTED at pre-wifi-unbind-l1`, completed steps undone in reverse, no undo errors |
| D6 alarm readback | `sudo erhai-lab dryrun --alarm 30` | `alarm-arm` completes (readback within 3 s of the request) |

**D3–D5 are suspended.** On 2026-10-21 the D3 run (`--wifi L1`, package
kernel b28) unbound `cnss_pci` while `wlan.ko` was loaded and the kernel
oopsed in the qcacld teardown, killing the writer: `Unable to handle kernel
paging request at virtual address 00656c6261746394`, `pc :
__mutex_lock.constprop.0`, call trace `hif_exec_napi_kill` ← `hif_exec_kill`
← `hif_pci_disable_isr` ← `hif_ce_stop` ← `htc_stop` ← `cds_post_disable` ←
`hdd_wlan_stop_modules` ← `hdd_wlan_exit` ← `wlan_hdd_pld_remove` ←
`pld_pcie_remove` ← `cnss_pci_call_driver_remove` ← `cnss_pci_dev_shutdown` ←
`cnss_pci_unregister_driver_hdlr` ← `cnss_pci_remove`. The same
`hif_exec_napi_kill` crash is recorded in the dev's `erhai-suspend-gnome.sh`
for a WLAN teardown racing suspend. Tearing the WCN host stack down on a live
system crashes without any sleep, so L1 cannot be used as designed; the next
step is a decision on how to remove Wi-Fi from the sleep path, if at all.

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
3. pmsg survives a **forced reset** (power + volume up) (covers the A/C/D/E endings):

       echo "erhai-lab E0 marker $(date +%s)" | sudo tee /dev/pmsg0
       sync; echo s | sudo tee /proc/sysrq-trigger
       # hold power + volume up until the tablet resets, boot the lab kernel again
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

**Result 2026-10-21 (package kernel b28): step 3 FAILED.** The pmsg marker did
not survive a forced reset (power + volume up), and `/sys/fs/pstore` was empty
after every boot that day, including clean `systemctl reboot`s and a boot that
had logged an oops: `/sys/kernel/reboot/mode` is `cold` and the ramoops region
at `0xa7800000` does not survive a cold reset on this firmware. A warm reboot
(`echo warm > /sys/kernel/reboot/mode; reboot`) **hangs** after `systemd-shutdown`
and needs a forced reset, so `reboot=warm` is not an option. Consequences until
a persistent channel is found: E1-E4.5 can still run (CPUs never stop and each
run saves dmesg to disk), but a hang or reset during a rung leaves only the
fsynced journal entry naming the rung; real-sleep rungs stay blocked.


## E1–E4.5: pm_test rungs (lab kernel, no real sleep)

`pm_test` makes the kernel walk the suspend path up to a level and come back
after 5 s, CPUs never stopping. Each run prints a verdict and saves dmesg and
readouts under `/var/lib/erhai-sleep/<bootid>/<ts>/`.

| Rung | pm_test | Command | Pass |
|---|---|---|---|
| E1 | freezer | `sudo erhai-lab probe --rung E1` | verdict `pass` |
| E2 | devices | `sudo erhai-lab probe --rung E2 --display park` (twice; Wi-Fi removal suspended) | `pass` both times |
| E3 | devices | `sudo erhai-lab probe --rung E3 --display park` | `pass` |
| E4 | platform | `sudo erhai-lab probe --rung E4 --display park` | `pass`; read the saved dmesg for `erhai-cc`/`pwrseq` lines: their presence means the host power-off path (b) runs |
| E4u | platform | if E4 fails: `--wifi L1`, then `--wifi L2` | first level that passes |
| E4.5 | platform | `sudo erhai-lab probe --rung E4.5 --display park --alarm 30` (holds pm_test for alarm + 10 s) | `rtc alarm irq: +1` and `pm_wakeup_irq` naming the alarm |

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
| A | no `resume-ok`, no panic; ended by the user's forced reset, power + volume up (wake never arrived) |
| abort | the attempt never entered sleep (guard fired or `suspend_stats.fail` moved) |

## Results log

**2026-10-21, lab kernel `00-debug` build 2**

- E1 pass (freezer). E2 pass once (devices, `--display park`): every driver
  suspended and resumed in ~40 ms; `dwc3_qcom_pm_resume returned -110` (USB
  controller resume timeout) logged but not counted as a failure;
  `cnss_pci` `pci_pm_suspend` returned after 4 µs, so the WCN's real suspend
  is not in the devices phase.
- In both passes the panel came back on ~1 s after `PM: suspend entry`
  (`nvt_ts_panel_power_on`), before tasks were frozen; the failed run logged
  `detected fb_set_par error, error code: -16` at the same point. Lead: the
  console (VT) switch at suspend entry makes DRM restore the display,
  undoing the GPU park + blank.
- **E2 second run: the tablet froze at suspend entry.** Cause, from the
  persistent journal of that boot: on `PrepareForSleep` NetworkManager took
  `wlp1s0` down, ~0.4 s later cnss ran the WLAN **idle shutdown**
  (`cnss: Doing idle shutdown`, qcacld `gInterfaceChangeWait` default 250 ms),
  and the idle shutdown oopsed in `hif_exec_napi_kill` (`kworker` in
  `cnss_driver_event_work` died holding a mutex, `exited with preempt_count 1`).
  The suspend entry 12 s later hung. Every attempt that day ran an idle
  shutdown before sleep and an idle restart after it; 2 of 3 completed, the
  third crashed. Same crash as the L1 dry run (`cnss_pci` unbind). The lab
  hook's psoc-timer freeze runs inside `systemd-suspend.service`, after
  NetworkManager's teardown, so it cannot prevent this.
- **Probe run with the qdf timers scaled (`timer_multiplier` 1000000 before
  `systemctl suspend`): no effect.** Every run still did an idle shutdown
  ~0.4 s after the probe started; `hdd_psoc_idle_timer_start()` passes
  `gInterfaceChangeWait` straight to `qdf_delayed_work_start()`, unscaled.
  Runs 1 and 2 passed; run 3 froze on the same oops (`hif_exec_napi_kill`,
  address `000001a400000034`). On both boots that crashed, it was the **third
  idle shutdown after boot**, with the same faulting address, so the crash
  looks deterministic per power-off/power-on cycle. Each idle restart also
  logged `notifier callback qcom_pcie_wcn_l1ss_notify already registered`.
- Next (D24 step 2): `gInterfaceChangeWait=0` in
  `/usr/lib/firmware/wlan/qca_cld/WCNSS_qcom_cfg.ini` disables the idle
  shutdown (`hdd_psoc_idle_timer_start`: "psoc idle timer is disabled").
- **E2 with `gInterfaceChangeWait=0` (idle shutdown disabled): the idle
  shutdown is gone** (`hdd_psoc_idle_timer_start: psoc idle timer is
  disabled`, 0 idle shutdowns in every run), **but the powered-up WCN does
  not survive the devices phase.** Run 1: `cnss: Failed to set MHI state:
  RESUME(7), err = -22`, `cnss_pci 0000:01:00.0: PM: pci_pm_resume returned
  -11 after 3652840 usecs` (the probe printed `pass`: resume errors were not
  counted; fixed). Runs 2-3: `__wlan_hdd_bus_suspend: Failed pmo bus suspend:
  8`, `cnss: Failed to suspend host driver, err = -16`, suspend aborted.
  Run 4 froze inside the devices phase, last line `wiphy_suspend` on `phy0`.
- Conclusion: both Wi-Fi paths into sleep fail on this kernel. With the idle
  shutdown, the WCN is powered off before sleep and the power-off crashes
  on the third cycle after boot; without it, the WCN's own bus suspend works
  once and its MHI resume fails, after which every later suspend is refused
  or hangs.
- **Candidate `50-wlan-napi-kill-once` (build 3), default Wi-Fi INI,
  `erhai-lab wifi-cycle --count 5`: 5/5 clean** (1 idle shutdown, 1 idle
  restart, 0 oopses, reconnected, per cycle). Its log shows the mechanism:
  each idle restart registers 18 `dp_intr` ext groups; each idle shutdown
  kills all 18 three times (`hif_exec_kill: 18 ext groups` twice, then the
  deregister path), i.e. 36 `already killed, skipping` per cycle. On the
  stock kernel every one of those repeat kills ran `netif_napi_del()` on a
  napi whose dummy netdev the first kill had freed, taking
  `netdev_lock(napi->dev)` on freed memory; the oops appeared once that
  memory was reused (the third idle shutdown after boot, twice).
- **Candidate 50, E2 x4 (devices): no freeze, no oops** (idle shutdown and
  restart each run). Every run logs one resume error: `gcc_usb30_prim_master_clk
  status stuck at 'off'` then `dwc3_qcom_pm_resume returns -16` (or -110);
  the same USB error was present on the stock kernel. Next candidate area.
- **Candidate 50, E4 (platform): all phases complete** (devices 36 ms, late
  5 ms, noirq 8.5 ms; resume noirq 20 ms, early 2 ms, devices 44 ms), no oops,
  only the USB resume error. `qcom-pcie 1c00000.pcie` `genpd_suspend_noirq`
  took 0.98 ms with no `erhai-cc` lines: the host power-off path (b) does not
  run in s2idle on this kernel (D3cold vetoed), as the design predicted.
- E4.5 first run (2026-10-21) was **invalid**: `pm_test_delay` is 5 s, so the
  system resumed after 5 s and the post hook cleared the 30 s alarm before it
  could fire. The probe now raises `pm_test_delay` to alarm + 10 s for the run.
- **Candidate 50, E4 second run: same as the first** (no oops, USB resume
  error only). **E4.5 (alarm 30 s, pm_test held 40 s): the RTC alarm fired
  and woke the system** (`rtc alarm irq: +1`, `pm_wakeup_irq: 220` =
  `pm8xxx_rtc_alarm`, `c400000.spmi:pmic@0:rtc@6100` wakeup events +2), with
  the same USB resume error. No-sleep rungs E1-E4.5 are complete on
  candidate 50.
- **Candidate 50, E5 (first real sleep, s2idle, alarm 120 s, one manual run
  per D26): the system slept and the RTC alarm woke it.** systemd-sleep
  22:57:46 to 22:59:48; timekeeping suspended 119 s in total (17 s2idle
  loop entries, longest 90.6 s); `pm_wakeup_irq: 220` (`pm8xxx_rtc_alarm`).
  No oops. The screen came back, **touch did not**, and the USB resume error
  is unchanged. Touch mechanism (from the saved dmesg): at suspend entry the
  console switch enables the panel 1 s after `PM: suspend entry`, which
  queues the NT36536 `resume_work`; the work downloads firmware while tasks
  freeze, then polls the IC after the SPI controller has suspended
  (`CTP_SPI_READ read error, ret=-108`, `nvt_check_fw_reset_state ...
  retry=51`) and still marks the IC awake. The panel disable in between
  skipped the touch sleep (the flag was not set yet), so after resume the
  panel enable logged `Touch is already resume` and never re-initialised the
  IC. Candidate `51-touch-suspend-sync` (= 50 + a touch patch) flushes
  `resume_work` before the panel-off hook decides and puts the IC to sleep
  in `nvt_pm_suspend`.
  Recovery confirmed the mechanism: the power button only switches the
  backlight (the panel stays enabled, so touch is not re-initialised), but a
  real panel cycle, `sudo ERHAI_SESSION_USER=<you>
  /usr/local/sbin/erhai-panel-power.sh off`, then `... on`, ran
  `nvt_ts_suspend` and then a full `nvt_ts_resume` (firmware download, no
  reset-state error, pen command accepted) and touch came back.
- **Candidate 51, E2: touch fine** (the panel-off hook slept the IC; full
  re-init on resume); USB resume error only. **E5 (alarm 120 s): the system
  slept and the RTC alarm woke it, screen and touch both came back**
  (confirmed by the user). One s2idle entry of 119.0 s (candidate 50's E5
  needed 17 entries), `pm_wakeup_irq` = `pm8xxx_rtc_alarm` (IRQ 235 this
  boot; the number changes between boots), no oops, Wi-Fi idle
  shutdown/restart clean, USB resume error only. The fix path ran as
  designed: the console switch again enabled the panel 1 s after suspend
  entry and queued `resume_work`; the panel-off hook now waited for it to
  finish (`nvt_ts_resume end` at 445.715171, `display off: sleeping NT36536`
  at 445.715260) and slept the IC on live rails, so the panel enable after
  resume ran a full re-init (firmware download, pen command acked).
- **USB resume error, root cause (code read, 2026-10-21).** In every saved
  run the first suspend of a boot fails the same way: `qmp_combo_usb_init`
  on resume logs `com_init ... count=1` (the erhai keep-alive left the
  common block up), then `phy initialization timed-out`, and
  `dwc3_qcom_pm_resume` returns -110. `usb_power_off()` clears `SW_PWRDN` in
  `PCS_POWER_DOWN_CONTROL` and only `com_init()` sets it again, which the
  keep-alive skips, so the PCS stays powered down. The
  `gcc_usb30_prim_master_clk status stuck at 'off'` / -16 variant only
  appears on later suspends of a boot whose USB already failed (secondary).
  It is not power loss: E2 (no noirq, no domain power-off) fails
  identically. Candidate `52-usb-pcs-power-up` (= 51 + a qmp-combo patch)
  sets `SW_PWRDN` at the start of `qmp_combo_usb_power_on`.
- **Candidate 52, E2: first clean `pass`** (no resume errors at all):
  `com_init ... count=1` again took the keep-alive path, but the PHY now
  reported ready and `dwc3_qcom_pm_resume` returned 0; gadget mode back.
  **E5 (alarm 120 s): `pass`**, one s2idle entry of 118.5 s, woken by
  `pm8xxx_rtc_alarm` (IRQ 232 this boot), screen, touch and USB came back
  (user-confirmed), Wi-Fi idle shutdown/restart clean, no oops. Open from
  this run: a Samsung T7 SSD left plugged in (USB host mode) through the
  sleep did not survive it: `xhci-hcd: WARNING: Host System Error`,
  `usb_dev_resume` took 2.65 s, then `USB disconnect` and a failed cache
  sync on `sdg`; a replug re-enumerated it at SuperSpeed Plus. Until that is
  fixed, eject USB storage before sleeping. The
  `notifier callback qcom_pcie_wcn_l1ss_notify already registered` warning
  after resume comes from every WLAN idle restart (also at 9 s, 32 s and
  128 s of this boot), not from sleep.
