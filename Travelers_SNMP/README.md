# Travelers SNMP — Synthetic Multi-Device Lab

Six SNMP agents of different system types on **127.0.0.1** with unique UDP ports.

## IP / port assignments

| # | Hostname | System type | IP | Port |
|---|----------|-------------|-----|------|
| 1 | `router-gw-01.example.com` | Cisco ISR 4331 / IOS XE 16.6.2 | `127.0.0.1` | `161` |
| 2 | `sw-core-01.travelers.lab` | Cisco Catalyst 9300 / IOS XE | `127.0.0.1` | `1162` |
| 3 | `sw-dist-02.travelers.lab` | Juniper EX4300 / JUNOS | `127.0.0.1` | `1163` |
| 4 | `app-web-03.travelers.lab` | Linux Ubuntu 22.04 | `127.0.0.1` | `1164` |
| 5 | `WIN-DC01.travelers.lab` | Windows Server 2022 | `127.0.0.1` | `1165` |
| 6 | `fw-edge-01.travelers.lab` | Palo Alto PA-3220 / PAN-OS | `127.0.0.1` | `1166` |

Full inventory: [`devices.md`](devices.md)

## Start

```bash
docker compose up -d
docker compose down
```

## Credentials

See [`credentials.env`](credentials.env).

| Protocol | Auth |
|----------|------|
| SNMPv2c | community `public` |
| SNMPv3 | user `user7`, authPriv, SHA/AES, passphrase `1234567890abcdef` |

## Smoke tests

```bash
snmpget -v2c -c public 127.0.0.1:161  sysDescr.0   # Cisco ISR
snmpget -v2c -c public 127.0.0.1:1162 sysDescr.0   # Catalyst
snmpget -v2c -c public 127.0.0.1:1163 sysDescr.0   # Juniper
snmpget -v2c -c public 127.0.0.1:1164 sysDescr.0   # Linux
snmpget -v2c -c public 127.0.0.1:1165 sysDescr.0   # Windows
snmpget -v2c -c public 127.0.0.1:1166 sysDescr.0   # Palo Alto
```
