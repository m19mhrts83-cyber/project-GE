#!/bin/bash
# Clear macOS Secure Input lock that blocks Alfred snippet expansion.
# Usage:
#   --status     show current lock
#   --relaunch   quit+reopen Cursor (helps if Cursor is the live holder)
#   --logout-gui soft: open logout dialog (user confirms)
#   --reset-gui  HARD: kill WindowServer (all GUI apps close → login screen)

set -euo pipefail

status() {
  python3 - <<'PY'
import ctypes, subprocess, re
lib = ctypes.CDLL('/System/Library/Frameworks/Carbon.framework/Carbon')
lib.IsSecureEventInputEnabled.restype = ctypes.c_bool
out = subprocess.check_output(['ioreg','-l','-w','0'], text=True, errors='replace')
m = re.search(r'kCGSSessionSecureInputPID"=(\d+)', out)
pid = m.group(1) if m else '0'
alive = subprocess.call(['kill','-0',pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)==0 if pid!='0' else False
print(f"SecureInput enabled={lib.IsSecureEventInputEnabled()} pid={pid} alive={alive}")
if pid != '0':
    subprocess.run(['ps','-p',pid,'-o','pid=,comm='], check=False)
PY
}

cmd="${1:---status}"
case "$cmd" in
  --status) status ;;
  --relaunch)
    nohup bash -c '
      sleep 2
      osascript -e "tell application \"Cursor\" to quit" || true
      for i in $(seq 1 40); do pgrep -x Cursor >/dev/null || break; sleep 0.5; done
      pkill -x Cursor 2>/dev/null || true
      sleep 1
      open -a Cursor
    ' >/dev/null 2>&1 &
    echo "Cursor relaunch scheduled."
    ;;
  --logout-gui)
    # Shows standard logout confirmation (safer)
    osascript -e 'tell application "System Events" to log out'
    ;;
  --reset-gui)
    echo "Killing WindowServer in 2s — all apps will close. Login screen next."
    sleep 2
    killall WindowServer
    ;;
  *)
    echo "Usage: $0 --status|--relaunch|--logout-gui|--reset-gui"
    exit 1
    ;;
esac
