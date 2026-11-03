# Installation

[English](setup.md) · [한국어](setup.ko.md) · [Overview](../README.md)

## Base system

Use 64-bit Raspberry Pi OS on a Pi 5. The tested runtime is Debian 13 / Python 3.13, with 8 GB RAM. Install the OS desktop for the on-device panel; headless web use does not need it. Keep the OS camera/display configuration matched to the physical connectors. The installer does not change boot firmware or device-tree overlays.

Clone into `~/hw-agent`, then run `bash scripts/install.sh` as your normal account. It installs OS packages, creates a system-site-packages virtual environment for Picamera2, installs direct Python dependencies, downloads verified vision/photo models, prompts for credentials and LAN CIDR, and installs the web/photo services and nginx entry points.

Choose a strong, unique dashboard password. `.env` has mode 600; `data/` has mode 700. `ALLOWED_HOSTS` must contain the hostnames/IPs you actually use. `LAN_CIDR` must be your trusted subnet, not an arbitrary example subnet. Change settings later with `.venv/bin/python scripts/configure.py --lang en` and restart services. Keep `SESSION_SECRET`: changing it invalidates login sessions and prevents decryption of existing OAuth tokens.

Deployment files contain placeholders. **Do not install files directly from `deploy/`.** `scripts/render-deployment.py` writes account-specific files into ignored `data/deploy/`. Installers use those rendered files and derive the Linux UID/GID rather than assuming 1000.

## Optional local model

Run `bash scripts/install-llm.sh`. It builds a pinned upstream llama.cpp revision, verifies a pinned Qwen3.5 4B Q4_K_M download, creates a private API key, and enables `alter-llm`. Allow several GB for weights and build files. A 5.8 GB service limit is configured for the 8 GB reference device; this is not a guarantee against memory pressure. See [model details](models.md).

## SMB

Set a Samba password separately with `sudo smbpasswd -a "$USER"`. The dashboard password is not the Samba password. Back up `/etc/samba/smb.conf` before changing existing shares. In its `[global]` section, keep guest access disabled, require SMB2 or later, restrict access to your LAN, and add:

```ini
include = /etc/samba/alter-shares.conf
```

Create the initially empty include if absent (`sudo touch /etc/samba/alter-shares.conf`), validate with `sudo testparm -s`, then restart `smbd`. Register shares under **Drives → SMB**. The helper only manages Alter shares. Open `\\<pi-host>\Alter-<share-name>` in Windows Explorer using the Pi Samba account. `wsdd2` provides Windows network discovery; direct UNC access is the fallback.

Mounts use filesystem UUIDs, not USB enumeration or mount-folder names. Index roots, photo roots and SMB shares are independent. Check permissions and free space before assuming an NTFS compression issue; [maintenance tools](ntfs-maintenance.md) are separate from installation.

## Touch panel and voice

From the Pi desktop account, run `bash scripts/install-startup.sh`. It enables available services, installs the `/panel` autostart and **Open Alter dashboard** desktop link, and installs display idle control. The project-root `Start-Alter.desktop` starts/checks services; the desktop link only opens Chromium. `./start.sh --no-browser` is suitable for SSH.

The idle timer uses local input activity (including remote desktop input), not server/API traffic. It dims after five minutes and restores brightness on input. It requires a detected backlight and compatible Wayland session. Camera orientation is in Settings; apply display orientation separately in Raspberry Pi OS.

For Korean speech, run `bash scripts/install-voice.sh` and connect a microphone recognized by the OS. Browser capture needs HTTPS or localhost. The popup keyboard supports Korean and English. Voice transcription/wake phrase currently remains Korean in either UI language. Wake listening uses repeated six-second recording/transcription, with gaps while processing; it is not a dedicated always-listening wake-word model.

## Remote access and SmartThings

[Connect using your own ngrok/OAuth credentials](oauth.md). Port 11977 is LAN-only. Port 8080 applies CAPTCHA, password login and DB-backed failed-login blocking. The reverse proxy overwrites exposure headers; the backend only trusts loopback proxy headers. Never expose the backend/model ports directly. Plain HTTP does not encrypt credentials: use the HTTPS endpoint for Internet access.

## Check an installation

Log in on 11977, switch language/theme, and confirm the overview updates without reloading. Add a folder containing synthetic test files and verify indexing, search and preview. Register a separate test SMB share; create/read/append/delete a synthetic file from Windows. Test the camera only when intended. For SmartThings, authorize your location, test a chosen device and restore its initial state. A successful health response alone does not verify hardware or account access.

Existing deployments and recovery: [operations](operations.md). Development tests run against disposable databases, not personal media: [contributor map](../readme-for-agent.md).

The display service currently targets `/sys/class/backlight/panel_backlight@1`. If the OS exposes a different backlight, adjust the service condition and `PANEL` in `scripts/display_brightness.py`. The desktop account must have write access to its `brightness` attribute through the OS device permissions; do not run the dashboard as root.
