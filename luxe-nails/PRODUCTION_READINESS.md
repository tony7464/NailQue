# NailQue Production Readiness

See the [root README](../README.md) for setup, security, and screenshots.

Before a salon launch:

1. Complete the first-run setup wizard (salon name + manager PIN that is not left at `1234`)
2. Build the installer (`./build-mac.sh` or `.\build-windows.ps1`)
3. Confirm `/`, `/employee`, `/mobile`, and `/api/health`
4. Create tech logins in Tech Management
5. Confirm queue assignment from the desk and from a phone, then finish a ticket and print the receipt
6. Optional: enable LAN HTTPS and sign/notarize the installer — [SIGNING.md](docs/SIGNING.md)
