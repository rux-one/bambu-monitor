# Bambu Monitor

Live web dashboard for Bambu Lab printers. Connects to each printer's local MQTT broker and streams status to a browser in real time.

## Requirements

- Python 3.10+
- Printers must be on the same local network
- LAN-only mode enabled on each printer (Bambu Studio → device settings)

## Setup

```bash
python -m venv venv
venv/bin/pip install -r requirements.txt
```

Copy the example config and fill in your printer details:

```bash
cp config.example.json config.json
```

```json
{
  "printers": [
    {
      "name": "A1-mini",
      "host": "192.168.1.117",
      "serial": "0309DA382100320",
      "access_code": "19783780"
    }
  ]
}
```

`config.json` is gitignored — credentials stay off disk.  
The serial and access code are visible in Bambu Studio under the device settings page.

## Run

```bash
venv/bin/python main.py
```

Open `http://localhost:8080` in a browser.

## Run as a service (survives SSH logout)

The repo includes a systemd user service file. Install it once:

```bash
# symlink into the user service directory
mkdir -p ~/.config/systemd/user
ln -sf "$(pwd)/bambu-monitor.service" ~/.config/systemd/user/bambu-monitor.service

# reload, enable (auto-start on boot), and start now
systemctl --user daemon-reload
systemctl --user enable --now bambu-monitor.service

# keep services alive after you log out of SSH
loginctl enable-linger "$USER"
```

### Common commands

| Action | Command |
|---|---|
| Check status | `systemctl --user status bambu-monitor` |
| Follow logs | `journalctl --user -u bambu-monitor -f` |
| Restart | `systemctl --user restart bambu-monitor` |
| Stop | `systemctl --user stop bambu-monitor` |
| Disable autostart | `systemctl --user disable bambu-monitor` |

## File overview

```
main.py                  # FastAPI app + MQTT clients
static/index.html        # self-contained frontend (no build step)
config.json              # your printer credentials (gitignored)
config.example.json      # template to copy
bambu-monitor.service    # systemd user service definition
requirements.txt         # Python dependencies
```
