#!/usr/bin/env bash
# Re-issue the Delhi air-quality bulletin after each 00/12 UTC analysis becomes available.
# crontab -e  ->  30 2,14 * * *  /path/to/run_delhi_aq_cron.sh >> /var/log/delhi_aq.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
python delhi_aq.py --mode foundry --hours 48 --plot --out "outputs/$(date -u +%Y-%m-%dT%H)" -v
