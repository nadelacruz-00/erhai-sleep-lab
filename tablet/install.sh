#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Install or remove the erhai-lab tablet kit.
#
#   sudo tablet/install.sh            install
#   sudo tablet/install.sh uninstall  remove everything, disarm, keep evidence
#
# Installs only: /usr/local/sbin/erhai-lab, the systemd-sleep caller and
# /var/lib/erhai-sleep. It does not arm anything: the suspend override is
# written per attempt by `erhai-lab probe` and removed afterwards (D19).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
SBIN=/usr/local/sbin/erhai-lab
HOOK=/usr/lib/systemd/system-sleep/erhai-lab
DROPIN=/etc/systemd/system/systemd-suspend.service.d/zz-erhai-lab.conf

[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }

case "${1:-install}" in
install)
	install -m 0755 "$HERE/erhai-lab" "$SBIN"
	install -D -m 0755 "$HERE/system-sleep/erhai-lab" "$HOOK"
	install -d -m 0755 /var/lib/erhai-sleep
	echo "installed $SBIN and $HOOK"
	;;
uninstall)
	if [ -e "$DROPIN" ]; then
		rm -f "$DROPIN"
		systemctl daemon-reload
		echo "removed $DROPIN"
	fi
	rm -f "$SBIN" "$HOOK"
	echo "removed $SBIN and $HOOK (evidence kept in /var/lib/erhai-sleep)"
	;;
*)
	echo "usage: $0 [install|uninstall]" >&2
	exit 2
	;;
esac
systemctl show -p ExecStart systemd-suspend.service | sed 's/ ; .*//'
