#!/usr/bin/env bash
set -euo pipefail

# ===== Config =====
# If docker-compose.yaml exists in current dir (cloned repo), use it; otherwise create fresh
if [ -f "docker-compose.yaml" ] || [ -f "docker-compose.yml" ]; then
  STACK_DIR="$(pwd)"
  echo ">>> Found existing docker-compose file, using current directory: $STACK_DIR"
else
  STACK_DIR="$HOME/home-pi"
  echo ">>> Setting up Pi homelab in: $STACK_DIR"
  mkdir -p "$STACK_DIR"
  cd "$STACK_DIR"
fi

# ----- Detect basics -----
PUID="$(id -u)"
PGID="$(id -g)"

if [ -f /etc/timezone ]; then
  TZ_DEFAULT="$(cat /etc/timezone)"
else
  TZ_DEFAULT="America/New_York"
fi

PI_IP="$(hostname -I | awk '{print $1}')"

# ===== Install Docker if needed =====
if ! command -v docker >/dev/null 2>&1; then
  echo ">>> Docker not found, installing via get.docker.com..."
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
  rm -f get-docker.sh
else
  echo ">>> Docker already installed."
fi

# Install docker compose plugin if needed
if ! docker compose version >/dev/null 2>&1; then
  echo ">>> docker compose plugin not found, installing..."
  sudo apt-get update
  sudo apt-get install -y docker-compose-plugin
else
  echo ">>> docker compose plugin already installed."
fi

# ===== Fix Docker Group Permissions =====
echo ">>> Configuring Docker permissions..."

# Ensure docker group exists
if ! getent group docker >/dev/null 2>&1; then
  echo ">>> Creating docker group..."
  sudo groupadd docker
fi

# Add current user to docker group if not already
if ! id -nG "$USER" | grep -qw "docker"; then
  echo ">>> Adding $USER to docker group..."
  sudo usermod -aG docker "$USER"
fi

# Fix docker socket permissions - this is critical for non-sudo access
if [ -S /var/run/docker.sock ]; then
  echo ">>> Fixing docker socket permissions..."
  sudo chown root:docker /var/run/docker.sock
  sudo chmod 660 /var/run/docker.sock
fi

# Function to run docker commands - uses sg if not yet in docker group in current session
run_docker() {
  if id -nG | grep -qw "docker" && [ -w /var/run/docker.sock ]; then
    # Already in docker group and socket is writable
    docker "$@"
  else
    # Use sg to run in docker group context (works without logout)
    sg docker -c "docker $*"
  fi
}

run_docker_compose() {
  if id -nG | grep -qw "docker" && [ -w /var/run/docker.sock ]; then
    docker compose "$@"
  else
    sg docker -c "docker compose $*"
  fi
}

# ===== Write .env if not present =====
if [ -f .env ]; then
  echo ">>> .env already exists, not overwriting."
else
  echo ">>> Creating .env with sensible defaults..."
  cat > .env <<EOF
# Timezone
TZ=$TZ_DEFAULT

# Linux user/group for LinuxServer-style containers
PUID=$PUID
PGID=$PGID

# Pi-hole
PIHOLE_PASSWORD=$(openssl rand -hex 16)
PIHOLE_HOSTNAME=pi-hole
PIHOLE_DOMAIN=home.lan
PIHOLE_DNS="1.1.1.1;1.0.0.1"

# Tailscale
# Generate an auth key at: https://login.tailscale.com/admin/settings/keys
# Use a reusable key if you want auto-reconnect after restarts
TS_AUTHKEY=

# Speedtest Tracker
# IMPORTANT: after first start, you'll need to generate a proper APP_KEY (see README output)
SPEEDTEST_APP_KEY=base64:change_me_after_first_run
SPEEDTEST_APP_URL=http://$PI_IP:8765

# Netdata
NETDATA_HOSTNAME=pi-netdata

# Webtop (remote desktop browser)
WEBTOP_USER=user
WEBTOP_PASSWORD=$(openssl rand -hex 16)
EOF
fi

echo ">>> Current .env:"
cat .env

# ===== Write docker-compose.yml if not present =====
if [ -f docker-compose.yml ] || [ -f docker-compose.yaml ]; then
  echo ">>> docker-compose file already exists, not overwriting."
else
  echo ">>> Writing docker-compose.yml..."
  cat > docker-compose.yml <<'EOF'
version: "3.9"

services:
  pihole:
    image: pihole/pihole:latest
    container_name: pihole
    hostname: ${PIHOLE_HOSTNAME:-pihole}
    domainname: ${PIHOLE_DOMAIN:-lan}
    network_mode: "host"
    environment:
      TZ: ${TZ}
      FTLCONF_webserver_api_password: ${PIHOLE_PASSWORD}
      FTLCONF_dns_dnssec: "true"
      FTLCONF_dns_listeningMode: "all"
      PIHOLE_DNS_: ${PIHOLE_DNS:-"1.1.1.1;1.0.0.1"}
    volumes:
      - ./pihole/etc-pihole:/etc/pihole
      - ./pihole/etc-dnsmasq.d:/etc/dnsmasq.d
    restart: unless-stopped

  tailscale:
    image: tailscale/tailscale:latest
    container_name: tailscale
    network_mode: "host"
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - ./tailscale/var-lib:/var/lib/tailscale
      - /dev/net/tun:/dev/net/tun
    environment:
      TS_STATE_DIR: /var/lib/tailscale
      TS_AUTHKEY: ${TS_AUTHKEY:-}
      TS_EXTRA_ARGS: "--accept-routes --accept-dns=false"
      TS_USERSPACE: "false"
    restart: unless-stopped

  homer:
    image: b4bz/homer:latest
    container_name: homer
    ports:
      - "0.0.0.0:8080:8080"
    volumes:
      - ./homer/assets:/www/assets
    environment:
      - INIT_ASSETS=1
      - TZ=${TZ}
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8080"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped

  speedtest-tracker:
    image: lscr.io/linuxserver/speedtest-tracker:latest
    container_name: speedtest-tracker
    ports:
      - "0.0.0.0:8765:80"
    environment:
      PUID: ${PUID}
      PGID: ${PGID}
      TZ: ${TZ}
      APP_KEY: ${SPEEDTEST_APP_KEY}
      APP_URL: ${SPEEDTEST_APP_URL}
      DB_CONNECTION: sqlite
      DISPLAY_TIMEZONE: ${TZ}
      SPEEDTEST_SCHEDULE: "0 */6 * * *"
      PRUNE_RESULTS_OLDER_THAN: 180
    volumes:
      - ./speedtest-tracker/config:/config
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  netdata:
    image: netdata/netdata:latest
    container_name: netdata
    hostname: ${NETDATA_HOSTNAME:-rpi-netdata}
    ports:
      - "0.0.0.0:19999:19999"
    cap_add:
      - SYS_PTRACE
    security_opt:
      - apparmor:unconfined
    volumes:
      - netdata_config:/etc/netdata
      - netdata_lib:/var/lib/netdata
      - netdata_cache:/var/cache/netdata
      - /etc/passwd:/host/etc/passwd:ro
      - /etc/group:/host/etc/group:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /etc/os-release:/host/etc/os-release:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:19999/api/v1/info"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  portainer:
    image: portainer/portainer-ce:latest
    container_name: portainer
    ports:
      - "0.0.0.0:9443:9443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - portainer_data:/data
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "--no-check-certificate", "https://localhost:9443"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  webtop:
    image: lscr.io/linuxserver/webtop:debian-xfce
    container_name: webtop
    ports:
      - "0.0.0.0:3000:3000"
      - "0.0.0.0:3002:3001"
    environment:
      - PUID=${PUID}
      - PGID=${PGID}
      - TZ=${TZ}
      - CUSTOM_USER=${WEBTOP_USER:-user}
      - PASSWORD=${WEBTOP_PASSWORD}
    volumes:
      - ./webtop/config:/config
    shm_size: "4g"
    security_opt:
      - seccomp:unconfined
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped

  uptime-kuma:
    image: louislam/uptime-kuma:latest
    container_name: uptime-kuma
    ports:
      - "0.0.0.0:3001:3001"
    volumes:
      - ./uptime-kuma/data:/app/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3001"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  watchtower:
    image: containrrr/watchtower:latest
    container_name: watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - TZ=${TZ}
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_SCHEDULE=0 0 4 * * *
      - WATCHTOWER_ROLLING_RESTART=true
    restart: unless-stopped

  dozzle:
    image: amir20/dozzle:latest
    container_name: dozzle
    ports:
      - "0.0.0.0:8888:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - TZ=${TZ}
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8080/healthcheck"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    restart: unless-stopped

volumes:
  netdata_config:
  netdata_lib:
  netdata_cache:
  portainer_data:
EOF
fi

# ===== Create data directories =====
echo ">>> Creating data directories..."
mkdir -p pihole/etc-pihole pihole/etc-dnsmasq.d
mkdir -p tailscale/var-lib
mkdir -p homer/assets
mkdir -p speedtest-tracker/config
mkdir -p webtop/config
mkdir -p uptime-kuma/data

# ===== Install Mullvad VPN (host) =====
echo ">>> Installing Mullvad VPN (host)..."
if ! command -v mullvad >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y curl
  sudo curl -fsSLo /usr/share/keyrings/mullvad-keyring.asc \
    https://repository.mullvad.net/deb/mullvad-keyring.asc
  echo "deb [signed-by=/usr/share/keyrings/mullvad-keyring.asc arch=$(dpkg --print-architecture)] https://repository.mullvad.net/deb/stable stable main" | \
    sudo tee /etc/apt/sources.list.d/mullvad.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y mullvad-vpn
else
  echo ">>> Mullvad already installed."
fi

echo
echo ">>> ==================================================="
echo ">>> IMPORTANT: Mullvad is installed but NOT logged in."
echo ">>> Run these manually ONCE:"
echo ">>>   mullvad account login YOUR-ACCOUNT-NUMBER"
echo ">>>   mullvad relay set tunnel-protocol wireguard"
echo ">>>   mullvad lan set allow    # CRITICAL: allows LAN access while VPN is connected"
echo ">>>   mullvad connect"
echo ">>> (Optionally: mullvad auto-connect set on)"
echo ">>> ==================================================="
echo
echo ">>> ==================================================="
echo ">>> TAILSCALE AUTHENTICATION"
echo ">>> ==================================================="
echo ">>> Option 1: Manual authentication (run once):"
echo ">>>   docker exec -it tailscale tailscale up"
echo ">>>   (Follow the URL to authenticate)"
echo ""
echo ">>> Option 2: Auth key (recommended for auto-reconnect):"
echo ">>>   1. Go to: https://login.tailscale.com/admin/settings/keys"
echo ">>>   2. Generate a reusable auth key"
echo ">>>   3. Add to .env: TS_AUTHKEY=tskey-auth-xxxxx"
echo ">>>   4. Restart: docker compose restart tailscale"
echo ">>> ==================================================="
echo

# ===== Start the stack =====
echo ">>> Pulling containers..."
run_docker_compose pull

echo ">>> Bringing stack up..."
run_docker_compose up -d

# ===== Wait for containers to start and run diagnostics =====
echo ">>> Waiting for containers to start (30 seconds)..."
sleep 30

echo
echo ">>> ==================================================="
echo ">>> DIAGNOSTICS: Container Status"
echo ">>> ==================================================="
run_docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo ">>> ==================================================="
echo ">>> DIAGNOSTICS: Port Bindings"
echo ">>> ==================================================="
echo ">>> Checking if services are listening on their ports..."

check_port() {
  local port=$1
  local name=$2
  if ss -tlnp 2>/dev/null | grep -q ":$port " || netstat -tlnp 2>/dev/null | grep -q ":$port "; then
    echo ">>>   [OK] $name (port $port) - LISTENING"
  else
    echo ">>>   [FAIL] $name (port $port) - NOT LISTENING"
  fi
}

check_port 80 "Pi-hole"
check_port 8080 "Homer"
check_port 8765 "Speedtest"
check_port 19999 "Netdata"
check_port 9443 "Portainer"
check_port 3000 "Webtop"
check_port 3001 "Uptime Kuma"
check_port 8888 "Dozzle"

echo
echo ">>> ==================================================="
echo ">>> DIAGNOSTICS: Health Status"
echo ">>> ==================================================="
run_docker ps --format "{{.Names}}: {{.Status}}" | grep -E "(healthy|unhealthy|starting)" || echo ">>> (Health checks still initializing...)"

echo
echo ">>> Done!"
echo ">>> Services:"
echo ">>>   Pi-hole:          http://$PI_IP/admin"
echo ">>>   Homer dashboard:  http://$PI_IP:8080"
echo ">>>   Speedtest:        http://$PI_IP:8765"
echo ">>>   Netdata:          http://$PI_IP:19999"
echo ">>>   Portainer:        https://$PI_IP:9443"
echo ">>>   Webtop Browser:   http://$PI_IP:3000 (user: WEBTOP_USER, pass: WEBTOP_PASSWORD in .env)"
echo ">>>   Uptime Kuma:      http://$PI_IP:3001 (service monitoring)"
echo ">>>   Dozzle:           http://$PI_IP:8888 (Docker logs viewer)"
echo ">>>   Watchtower:       Auto-updates containers at 4 AM daily"
echo
echo ">>> Since your Pi has a desktop + Chromium, you can also open those URLs directly in Chromium on the Pi."
echo ">>> For remote access, consider using Tailscale (container already running)."
echo
echo ">>> Next recommended steps:"
echo ">>>  1) Authenticate Tailscale: docker exec -it tailscale tailscale up"
echo ">>>  2) Log in to Mullvad as above and connect."
echo ">>>  3) Log in to Pi-hole and set Pi-hole as DNS on your router."
echo ">>>  4) Configure Pi-hole blocklists (I'll list good defaults in the README / notes)."
echo ">>> ==================================================="
echo
echo ">>> ==================================================="
echo ">>> TROUBLESHOOTING COMMANDS"
echo ">>> ==================================================="
echo ">>> If ports are not working, run these to diagnose:"
echo ">>>   docker ps                    # Check container status"
echo ">>>   docker logs <container>      # Check container logs"
echo ">>>   ss -tlnp | grep <port>       # Check if port is listening"
echo ">>>   curl -v localhost:<port>     # Test local connectivity"
echo ">>> ==================================================="
