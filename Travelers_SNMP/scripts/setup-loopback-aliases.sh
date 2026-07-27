#!/usr/bin/env bash
# Add macOS loopback aliases so each synthetic device can bind :161 on its own IP.
set -euo pipefail

ALIASES=(127.0.0.2 127.0.0.3 127.0.0.4 127.0.0.5 127.0.0.6)

echo "Adding loopback aliases (requires sudo)..."
for ip in "${ALIASES[@]}"; do
  if ifconfig lo0 | grep -q "inet ${ip} "; then
    echo "  ${ip} already present"
  else
    sudo ifconfig lo0 alias "${ip}" netmask 0xff000000
    echo "  added ${ip}"
  fi
done

echo
echo "Loopback SNMP targets:"
printf "  %-16s  %s\n" "127.0.0.1" "Cisco ISR 4331 (IOS XE)"
printf "  %-16s  %s\n" "127.0.0.2" "Cisco Catalyst 9300"
printf "  %-16s  %s\n" "127.0.0.3" "Juniper EX4300"
printf "  %-16s  %s\n" "127.0.0.4" "Linux Ubuntu server"
printf "  %-16s  %s\n" "127.0.0.5" "Windows Server 2022"
printf "  %-16s  %s\n" "127.0.0.6" "Palo Alto PA-3220"
echo "All devices: UDP port 161"
