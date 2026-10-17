# scripts/ — 311

本線: `~/git-repos/scripts/jarvis_send_gate_311.py`  
ラッパ: `./run_gate.sh --draft … --source manual --dry-run`

```bash
# 経路B
~/selenium_env/venv/bin/python ~/git-repos/scripts/jarvis_send_gate_311.py \
  --draft '/path/4.送信下書き.txt' --source manual --dry-run

# 経路A（inbox 1回）
~/selenium_env/venv/bin/python ~/git-repos/scripts/jarvis_send_gate_311.py --from-inbox --dry-run
~/selenium_env/venv/bin/python ~/git-repos/scripts/jarvis_send_gate_311.py --from-inbox --post

# 上流キック（Phase3）
~/selenium_env/venv/bin/python ~/git-repos/scripts/jarvis_send_gate_311.py \
  --enqueue --draft '/path/4.送信下書き.txt' --source hawk

# 定常（15分）
~/git-repos/launchd/install_send_gate_311_inbox_poll_launchd.sh
# 解除: …/uninstall_send_gate_311_inbox_poll_launchd.sh
# 無効化のみ: JARVIS_SEND_GATE_311_POLL_DISABLE=1
```

