# 🏠 Pi Homelab – Privacy Stack + Remote Browser

> **One-command setup** for a privacy-focused Raspberry Pi 5 homelab with ad-blocking, VPN, remote browser, and monitoring.

---

## ⚡ Quick Start

```bash
# On your Pi (SSH or terminal)
git clone https://github.com/<yourname>/home-pi.git
cd home-pi && ./setup.sh
```

Then manually connect Mullvad VPN:

```bash
sudo mullvad account login YOUR-ACCOUNT-NUMBER
sudo mullvad connect
```

**Done!** Your Pi is now a privacy gateway.

---

## 📋 Quick Reference Card

### 🔗 All Service URLs

| Service | URL | Login |
|---------|-----|-------|
| **Pi-hole** | `http://PI-IP/admin` | Password in `.env` → `PIHOLE_PASSWORD` |
| **Homer** | `http://PI-IP:8080` | — |
| **Speedtest** | `http://PI-IP:8765` | First-run setup |
| **Netdata** | `http://PI-IP:19999` | — |
| **Portainer** | `https://PI-IP:9443` | First-run setup |
| **Webtop** | `http://PI-IP:3000` | `.env` → `WEBTOP_USER` / `WEBTOP_PASSWORD` |
| **Uptime Kuma** | `http://PI-IP:3001` | First-run setup |
| **Dozzle** | `http://PI-IP:8888` | — |

> 💡 **Find your Pi's IP:** Run `hostname -I` on the Pi

### 🔑 Where Are My Passwords?

```bash
cat .env | grep PASSWORD
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        YOUR NETWORK                              │
│                                                                  │
│   📱 Phone ──┐                                                   │
│   💻 Laptop ─┼──► Router ──► Pi-hole (DNS) ──► Mullvad VPN ──► 🌐│
│   📺 TV ─────┘        │           │                              │
│                       │           ▼                              │
│               ┌───────┴───────────────────────┐                  │
│               │     RASPBERRY PI 5            │                  │
│               │  ┌─────────────────────────┐  │                  │
│               │  │ Docker Containers       │  │                  │
│               │  │ • Pi-hole     • Netdata │  │                  │
│               │  │ • Tailscale  • Portainer│  │                  │
│               │  │ • Homer      • Webtop   │  │                  │
│               │  │ • Speedtest  • Uptime   │  │                  │
│               │  │ • Watchtower • Dozzle   │  │                  │
│               │  └─────────────────────────┘  │                  │
│               │  Mullvad VPN (host)           │                  │
│               └───────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

**Traffic flow:** All devices → Pi-hole (ads blocked) → Mullvad VPN → Internet

---

## 🧩 What's Included

| Service | What It Does | Why You Want It |
|---------|--------------|-----------------|
| **Pi-hole** | Blocks ads & trackers at DNS level | No more YouTube ads on your TV |
| **Mullvad VPN** | Encrypts all outbound traffic | Your ISP can't see what you do |
| **Tailscale** | Secure remote access to your home | Access Pi-hole from anywhere |
| **Webtop** | Full remote desktop with Firefox | Private browser from any device |
| **Homer** | Dashboard showing all services | One page to access everything |
| **Netdata** | Real-time Pi health metrics | See CPU, RAM, temp, network |
| **Speedtest Tracker** | Automated internet speed tests | Prove your ISP is lying |
| **Portainer** | Docker management UI | Easy container control |
| **Uptime Kuma** | Service monitoring + alerts | Know when something breaks |
| **Dozzle** | Live Docker log viewer | Debug issues fast |
| **Watchtower** | Auto-updates containers | Set and forget |

---

## 📦 Installation

### Prerequisites

- Raspberry Pi 5 (or Pi 4) with **Raspberry Pi OS 64-bit**
- Internet connection
- Mullvad VPN account (optional but recommended)

### Step 1: Run Setup

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/<yourname>/home-pi.git
cd home-pi
chmod +x setup.sh
./setup.sh
```

The script automatically:
- ✅ Installs Docker + Compose
- ✅ Installs Mullvad VPN
- ✅ Generates secure random passwords
- ✅ Creates all config directories
- ✅ Pulls and starts all 10 containers

### Step 2: Connect Mullvad VPN

```bash
sudo mullvad account login YOUR-ACCOUNT-NUMBER
sudo mullvad relay set tunnel-protocol wireguard
sudo mullvad connect
sudo mullvad lan allow  # Keep LAN access working
```

Verify it's working:

```bash
mullvad status          # Should say "Connected"
curl https://ifconfig.io  # Should show Mullvad IP, not your home IP
```

### Step 3: Post-Install Checklist

- [ ] **Pi-hole**: Set your router's DNS to your Pi's IP
- [ ] **Pi-hole**: Add blocklists (see below)
- [ ] **Tailscale**: Run `docker exec -it tailscale tailscale up` and authenticate
- [ ] **Portainer**: Visit `https://PI-IP:9443` and create admin account
- [ ] **Uptime Kuma**: Visit `http://PI-IP:3001` and create admin account
- [ ] **Speedtest**: Generate APP_KEY if prompted (see Troubleshooting)

---

## 🧱 Pi-hole Configuration

### Access

```
http://PI-IP/admin
```

Password: Check `.env` file for `PIHOLE_PASSWORD`

### Router Setup

Set your router's **DHCP DNS server** to your Pi's IP address. This makes all devices on your network use Pi-hole automatically.

### Recommended Blocklists

Go to **Group Management → Adlists** and add:

| List | URL |
|------|-----|
| StevenBlack Unified | `https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts` |
| HaGeZi Pro | `https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt` |
| OISD | `https://big.oisd.nl/` |
| Smart TV Telemetry | `https://raw.githubusercontent.com/Perflyst/PiHoleBlocklist/master/SmartTV.txt` |

After adding, go to **Tools → Update Gravity**.

---

## 🔐 Tailscale Setup (Remote Access)

### Initial Login

```bash
docker exec -it tailscale tailscale up
```

Click the link to authenticate with your Tailscale account.

### Make Pi an Exit Node (Route All Traffic Through Pi)

```bash
docker exec -it tailscale tailscale up \
  --accept-dns=false \
  --advertise-exit-node \
  --advertise-routes=192.168.1.0/24
```

Then in [Tailscale Admin Console](https://login.tailscale.com/admin/machines):
1. Approve the subnet route
2. Enable as Exit Node

Now on your phone/laptop, you can toggle **Use Exit Node → Your Pi** to route all traffic through your Pi (and Mullvad).

---

## 🌐 Remote Browser (Webtop)

Access a full Firefox browser running on your Pi from any device:

```
http://PI-IP:3000   (HTTP)
https://PI-IP:3002  (HTTPS)
```

**Credentials:** Check `.env` for `WEBTOP_USER` and `WEBTOP_PASSWORD`

This is useful for:
- Private browsing that goes through Mullvad
- Accessing your home network services remotely
- Isolating sketchy websites from your main computer

---

## 🛠️ Common Commands

### Container Management

```bash
# View all running containers
docker ps

# Stop everything
docker compose down

# Start everything
docker compose up -d

# Restart a specific service
docker compose restart pihole

# View logs for a service
docker logs -f pihole

# Update all containers
docker compose pull && docker compose up -d
```

### Mullvad VPN

```bash
mullvad status              # Check connection status
mullvad connect             # Connect to VPN
mullvad disconnect          # Disconnect
mullvad relay list          # List available servers
mullvad relay set location us nyc  # Set specific location
mullvad lan allow           # Allow LAN access while connected
```

### Tailscale

```bash
docker exec -it tailscale tailscale status    # Check status
docker exec -it tailscale tailscale ip        # Get Tailscale IP
docker exec -it tailscale tailscale ping <device>  # Test connectivity
```

---

## 📊 Resource Usage (Pi 5 16GB)

| Service | RAM | CPU | Notes |
|---------|-----|-----|-------|
| Pi-hole | ~100MB | Minimal | Lightweight |
| Tailscale | ~50MB | Minimal | Lightweight |
| Homer | ~30MB | Minimal | Static dashboard |
| Speedtest | ~150MB | Spikes during tests | Every 6 hours |
| Netdata | ~200MB | ~5% | Continuous monitoring |
| Portainer | ~100MB | Minimal | |
| Webtop | ~500MB-2GB | Variable | Depends on browser usage |
| Uptime Kuma | ~100MB | Minimal | |
| Dozzle | ~50MB | Minimal | |
| Watchtower | ~30MB | Minimal | |
| **Total** | **~1.5-3GB** | **<20%** | Plenty of headroom |

Your Pi 5 with 16GB RAM can easily handle this stack plus more services if needed.

---

## 🚑 Troubleshooting

### Pi-hole not blocking ads

1. Verify your device is using Pi-hole as DNS:
   ```bash
   nslookup google.com    # Should show your Pi's IP as server
   ```
2. Check router DHCP settings point to Pi's IP
3. Some devices have hardcoded DNS (Google Home, Chromecast) - block 8.8.8.8 and 8.8.4.4 on your router

### Webtop not loading

1. Check container is running: `docker ps | grep webtop`
2. View logs: `docker logs webtop`
3. If using HTTPS (port 3002), accept the self-signed certificate

### Mullvad connected but websites don't work

```bash
sudo mullvad lan allow  # Allow local network access
```

### DNS is leaking (not going through VPN)

Pi-hole DNS queries go through Mullvad when:
- Mullvad is connected on the host
- Pi-hole uses external DNS (1.1.1.1, etc.) as upstream

Verify with: `curl https://ipleak.net/json/`

### Speedtest Tracker asks for APP_KEY

Generate a new key:

```bash
docker exec -it speedtest-tracker php artisan key:generate --show
```

Copy the output to `.env` as `SPEEDTEST_APP_KEY=<key>`, then restart:

```bash
docker compose restart speedtest-tracker
```

### Container won't start

```bash
docker logs <container-name>  # Check for errors
docker compose down && docker compose up -d  # Full restart
```

### Tailscale can't connect

```bash
docker exec -it tailscale tailscale up --reset  # Reset and re-auth
```

### Out of disk space

```bash
docker system prune -a  # Remove unused images/containers
```

---

## 🔄 Maintenance

### Watchtower (Automatic Updates)

Watchtower runs daily at 4 AM and automatically updates containers. Check what it's done:

```bash
docker logs watchtower
```

### Manual Updates

```bash
cd ~/home-pi
docker compose pull
docker compose up -d
```

### Backup

Important data to backup:
- `~/home-pi/.env` (passwords)
- `~/home-pi/pihole/` (Pi-hole config)
- `~/home-pi/uptime-kuma/` (monitors)

---

## 🧭 Usage Scenarios

### 🔒 Mode 1: Whole-Home Ad Blocking
- Set router DNS to Pi-hole
- All devices get ad-free browsing automatically

### 🌐 Mode 2: Private Browsing via Webtop
- Access `http://PI-IP:3000` from any device
- Browse through Mullvad VPN with Pi-hole filtering

### 📱 Mode 3: Mobile Privacy via Tailscale
- Enable Pi as Tailscale Exit Node
- On your phone, toggle "Use Exit Node"
- All phone traffic → Pi → Mullvad

### 🏠 Mode 4: Remote Home Access
- Connect to Tailscale from anywhere
- Access all your home services securely
- No port forwarding needed

---

## 📁 File Structure

```
~/home-pi/
├── docker-compose.yaml    # Container definitions
├── setup.sh               # One-command installer
├── .env                   # Passwords and config (auto-generated)
├── pihole/                # Pi-hole data
├── tailscale/             # Tailscale state
├── homer/                 # Dashboard config
├── speedtest-tracker/     # Speed test history
├── webtop/                # Remote desktop config
└── uptime-kuma/           # Monitoring data
```

---

## 🆘 Getting Help

- **Pi-hole**: [docs.pi-hole.net](https://docs.pi-hole.net)
- **Tailscale**: [tailscale.com/kb](https://tailscale.com/kb)
- **Mullvad**: [mullvad.net/help](https://mullvad.net/help)
- **Uptime Kuma**: [github.com/louislam/uptime-kuma](https://github.com/louislam/uptime-kuma)

---

**Built for Raspberry Pi 5 (16GB) with 256GB storage** • All containers are ARM64 native
