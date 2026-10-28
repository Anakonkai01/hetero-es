#!/bin/bash
# Deletes the agreed old HeteroES research leftovers in Thao's WSL (owner's "đồng ý", 2026-10-21 ~19:45 +07).
# Keeps heteroes-c4-cpu (the CPU coordinator), heteroes-power and /tmp/heteroes-r11-c9* for the flag-day smoke run.
# Run from the 5070 Ti over SSH to Thao's WSL: ssh <thao-wsl> 'bash -s' < delete-wsl-leftovers.sh
set -u
cd "$HOME"
for p in heteroes-venv projects/heteroes .cache/huggingface .cache/heteroes .local/share/heteroes-m2 .config/heteroes-m2-agent \
         /tmp/heteroes-r11-c7 /tmp/heteroes-r11-c7-verify /tmp/heteroes-r11-c8 /tmp/heteroes-r11-c8-copy; do
  if [ -e "$p" ]; then
    s=$(du -sh "$p" | cut -f1)
    rm -rf -- "$p"
    if [ -e "$p" ]; then echo "FAILED $p"; else echo "deleted $p $s"; fi
  else
    echo "absent $p"
  fi
done
rmdir projects 2>/dev/null && echo "removed empty ~/projects"
echo "kept:"
du -sh .local/share/heteroes-c4-cpu .local/share/heteroes-power /tmp/heteroes-r11-c9 /tmp/heteroes-r11-c9-copy 2>&1
df -h / | tail -1
