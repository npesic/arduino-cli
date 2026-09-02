#!/bin/bash
# Health monitor for streamer.py crashes on the Pi Zero W.
# Run in a second terminal while streamer.py is running:
#   ./camdiag.sh | tee /tmp/health.log
# Logs free memory, streamer RSS, throttle/undervoltage flags and temp
# once a second, so state right before an unlogged kill is visible.

printf '%-8s %-9s %-9s %-11s %-6s\n' TIME AVAIL_MB RSS_MB THROTTLED TEMP
while true; do
    avail=$(awk '/^MemAvailable:/{printf "%d", $2/1024}' /proc/meminfo)
    rss=$(ps -o rss= -C python3 2>/dev/null | awk '{s+=$1} END{printf "%d", s/1024}')
    thr=$(vcgencmd get_throttled | cut -d= -f2)
    tmp=$(vcgencmd measure_temp | cut -d= -f2)
    printf '%-8s %-9s %-9s %-11s %-6s\n' "$(date +%T)" "$avail" "${rss:-0}" "$thr" "$tmp"
    sleep 1
done
