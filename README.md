# erhai-sleep-lab

A test lab for suspend/resume on the OnePlus Pad 3 (`erhai`, Snapdragon 8 Elite
/ SM8750) running Ubuntu on the mainline port at
[TheMojoMan/oneplus-erhai-linux](https://github.com/TheMojoMan/oneplus-erhai-linux).

On that port the tablet enters suspend but never comes back. The lab's first
job is to find out **how** it fails, not to guess: every sleep attempt leaves a
record that survives a forced restart, and the next boot files it as one of a
small set of failure classes (wake never arrived, a driver hung on resume, a
silent reset during entry or during resume, or resume completed with the panel
dark). Candidate fixes are then tested one CI-built kernel at a time.

## How it works

- **CI** (`.github/workflows/kernel.yml`) builds each directory under
  `candidates/` from a pinned commit of the port's kernel tree, using the
  tree's own `build-kernel.sh`, with the candidate's patches and config
  fragment and a `-lab-<candidate>` kernelrelease. Every requested config
  symbol is asserted in the final `.config`. The result is published as a
  Release: a UKI, a modules tarball, the `.config` and `SHA256SUMS`.
- **`erhai-lab`** (`tablet/erhai-lab`, one stdlib-only python3 tool) runs on
  the tablet. `erhai-lab fetch <candidate>` downloads a release, verifies every
  checksum and the UKI/modules version match, and installs the kernel *beside*
  the package kernel. rEFInd lists it as a second entry; its default is never
  changed.

## Safety contract

- A lab kernel is never installed with `dpkg`; it only adds
  `/boot/<kver>-lab-<candidate>.efi` and `/usr/lib/modules/<kver>-lab-<candidate>/`.
- Reverting is always a forced restart and picking the package kernel in the
  rEFInd menu.
- The suspend override that routes a sleep through the lab exists only while
  an attempt is armed (`erhai-lab arm` / `disarm`); otherwise the port's own
  suspend path runs untouched.
- Real-sleep rungs run only on a PM-debug kernel and only after the no-sleep
  rungs pass. The protocol is in `docs/ladder.md` (in progress).

## Status

Wave 1a in progress: CI and the `00-debug` candidate (PM debug, DPM watchdog,
`mem_sleep_default=s2idle`, `pm_debug_messages`, `no_console_suspend`);
`erhai-lab fetch`, `arm`, `disarm`, `plan`. The hook, probe, harvester and
classifier follow.

## Tests

    python3 -m unittest discover -s tests -v

## License

GPL-2.0-only.
