#!/bin/bash
set -e

echo "[clean-aa] Starting LIVI..."
systemctl --user start livi.service

echo "[clean-aa] Done. Check:"
echo "[clean-aa]   systemctl --user status livi.service -l -n 40 --no-pager"
