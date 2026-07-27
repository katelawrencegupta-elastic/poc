# Travelers SNMP lab — device inventory
# Credentials: SNMPv2c community "public" | SNMPv3 user7 / SHA+AES / 1234567890abcdef

| # | Hostname | System type | IP | Port | Container |
|---|----------|-------------|-----|------|-----------|
| 1 | router-gw-01.example.com | Cisco ISR 4331 / IOS XE 16.6.2 | 127.0.0.1 | 161/udp | travelers-cisco-ios-router |
| 2 | sw-core-01.travelers.lab | Cisco Catalyst 9300 / IOS XE | 127.0.0.1 | 1162/udp | travelers-cisco-catalyst |
| 3 | sw-dist-02.travelers.lab | Juniper EX4300 / JUNOS | 127.0.0.1 | 1163/udp | travelers-juniper-ex |
| 4 | app-web-03.travelers.lab | Linux Ubuntu 22.04 / net-snmp | 127.0.0.1 | 1164/udp | travelers-linux-server |
| 5 | WIN-DC01.travelers.lab | Windows Server 2022 | 127.0.0.1 | 1165/udp | travelers-windows-server |
| 6 | fw-edge-01.travelers.lab | Palo Alto PA-3220 / PAN-OS | 127.0.0.1 | 1166/udp | travelers-paloalto-fw |

## Optional: unique IPs all on port 161

```bash
./scripts/setup-loopback-aliases.sh   # sudo once
# then remap compose ports to 127.0.0.2:161 … 127.0.0.6:161
```
