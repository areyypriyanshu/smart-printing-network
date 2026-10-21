#!/usr/bin/env bash
#
# Make the home server behave like a small EC2 instance.
#
# The box is a CasaOS host: it has a home server panel on port 80 and
# runs its own Docker apps. This script therefore does NOT install a
# firewall by default. Two reasons:
#
#   1. Enabling ufw on a CasaOS host can cut the panel off from its own
#      services, because the panel talks to them over the LAN interface.
#   2. Docker publishes ports straight past ufw, so a firewall in front
#      of Docker is a false comfort. The meaningful protection here is
#      that the box is behind a home router with no port forwarding, and
#      that the site is published through an outbound tunnel.
#
# Pass --firewall to install ufw anyway, and read the CasaOS warning in
# the runbook first.
#
# The script is idempotent: run it twice and the second run changes
# nothing. It never reboots and never stops Docker's existing
# containers, so CasaOS keeps serving throughout.
#
#   sudo infra/home/bootstrap.sh [--firewall] [--skip-docker-restart]
#
# --skip-docker-restart applies the new daemon settings without
# restarting Docker. The new container log limits only apply to
# containers created afterwards, so the stack this script is preparing
# gets them either way. The restart is what applies them to the
# containers that already exist, and what turns live-restore on, and it
# is left to the operator when the machine is running someone else's
# apps.

set -euo pipefail

LOG_PREFIX="[bootstrap]"

log() { echo "${LOG_PREFIX} $*"; }
warn() { echo "${LOG_PREFIX} WARNING: $*" >&2; }
die() { echo "${LOG_PREFIX} ERROR: $*" >&2; exit 1; }

RUN_AS_SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then
    command -v sudo >/dev/null || die "this script needs root, and sudo is not installed"
    RUN_AS_SUDO="sudo"
fi

FIREWALL=0
SKIP_DOCKER_RESTART=0
for arg in "$@"; do
    case "$arg" in
        --firewall) FIREWALL=1 ;;
        --skip-docker-restart) SKIP_DOCKER_RESTART=1 ;;
        *) die "unknown option: $arg" ;;
    esac
done

# ---------------------------------------------------------------------
# What the machine is
# ---------------------------------------------------------------------

log "reading the machine"
MEM_TOTAL_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
CPU_MODEL=$(awk -F': ' '/model name/ {print $2; exit}' /proc/cpuinfo)
ARCH=$(uname -m)
log "  memory: ${MEM_TOTAL_MB} MB"
log "  processor: ${CPU_MODEL} (${ARCH})"

if [[ "${ARCH}" != "x86_64" ]]; then
    warn "this box is ${ARCH}, not x86_64. The PostGIS image this project"
    warn "uses is published for amd64 only, so the database would have to"
    warn "run under emulation. See docs/DEPLOY_HOME.md."
fi

# ---------------------------------------------------------------------
# Swap
#
# 4 GB of RAM with a database, a worker and a CasaOS panel on it is not
# enough to be comfortable. Swap is what keeps a memory spike from
# turning into an OOM kill of the database, which is the one container
# that cannot be restarted without losing something.
# ---------------------------------------------------------------------

SWAP_SIZE_MB=$((MEM_TOTAL_MB))
if swapon --show=NAME --noheadings | grep -q .; then
    log "swap is already on:"
    swapon --show | tail -n +2 | while read -r name _; do log "  $name"; done
else
    log "creating a ${SWAP_SIZE_MB} MB swap file on /var"
    fallocate -l "${SWAP_SIZE_MB}M" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    if ! grep -q '^/swapfile ' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    log "swap is on"
fi

# The kernel should not move pages to a spinning disk until it has to.
# 10 keeps the disk as a last resort instead of a habit.
cat > /etc/sysctl.d/60-spn-small-host.conf <<'EOF'
# Tuned for a 4 GB home server with a spinning disk.
#
# The swap file is a safety net, not a working space. vm.swappiness=10
# keeps the kernel from moving pages to a slow disk while there is still
# free memory to use.
vm.swappiness=10

# Do not keep too much of the page cache for writeback, because the
# disk is the bottleneck and the database's own cache is what matters.
vm.dirty_ratio=15
vm.dirty_background_ratio=5

# A low background writeback threshold means the disk is not allowed to
# fall far behind, which is what a long stall on an upload looks like.
vm.vfs_cache_pressure=50

# A 1 TB disk and 4 GB of RAM will hit the file descriptor limit long
# before it runs out of inodes.
fs.file-max=131072
EOF
${RUN_AS_SUDO} sysctl --system >/dev/null
log "kernel settings applied"

# ---------------------------------------------------------------------
# Security updates without being asked
# ---------------------------------------------------------------------

log "installing unattended security updates"
export DEBIAN_FRONTEND=noninteractive
${RUN_AS_SUDO} apt-get update -qq
${RUN_AS_SUDO} apt-get install -y -qq unattended-upgrades >/dev/null
${RUN_AS_SUDO} dpkg-reconfigure --priority=low unattended-upgrades >/dev/null 2>&1 || true

if [[ ! -f /etc/apt/apt.conf.d/20auto-upgrades ]]; then
    cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
fi
log "  security updates will install themselves"

# ---------------------------------------------------------------------
# Clock
#
# A wrong clock breaks TLS, and TLS is what the site is made of.
# ---------------------------------------------------------------------

log "making sure the clock is right"
if ! timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
    ${RUN_AS_SUDO} timedatectl set-ntp true 2>/dev/null || \
        ${RUN_AS_SUDO} apt-get install -y -qq systemd-timesyncd >/dev/null 2>&1 || true
fi
${RUN_AS_SUDO} timedatectl set-timezone UTC 2>/dev/null || true
log "  timezone is UTC, which is what the application stores"

# ---------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------

install_docker() {
    log "installing Docker from Docker's own repository"
    for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
        ${RUN_AS_SUDO} apt-get remove -y "$pkg" >/dev/null 2>&1 || true
    done
    ${RUN_AS_SUDO} apt-get install -y -qq ca-certificates curl >/dev/null
    ${RUN_AS_SUDO} install -m 0755 -d /etc/apt/keyrings
    ${RUN_AS_SUDO} curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    ${RUN_AS_SUDO} chmod a+r /etc/apt/keyrings/docker.asc
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
        | ${RUN_AS_SUDO} tee /etc/apt/sources.list.d/docker.list > /dev/null
    ${RUN_AS_SUDO} apt-get update -qq
    ${RUN_AS_SUDO} apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
}

if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
    log "Docker is already installed: $(docker --version)"
else
    install_docker
    log "  $(docker --version)"
fi

${RUN_AS_SUDO} systemctl enable --now docker >/dev/null 2>&1 || true

# The account that gets the Docker group is the one that asked for it.
# sudo resets USER to root, so the account that ran the script is taken
# from SUDO_USER instead, and only when there is one.
TARGET_USER="${SUDO_USER:-${USER}}"
if [[ -n "${RUN_AS_SUDO}" ]] && ! id -nG "${TARGET_USER}" | tr ' ' '\n' | grep -qx docker; then
    ${RUN_AS_SUDO} usermod -aG docker "${TARGET_USER}"
    log "  added ${TARGET_USER} to the docker group (log out and back in for it to take effect)"
fi

# ---------------------------------------------------------------------
# Docker daemon
#
# The log driver is the setting that matters most on a 1 TB disk that
# has to hold a database. Without a rotation every container log grows
# until the disk is full, and a full disk takes the database down.
# ---------------------------------------------------------------------

log "tuning the Docker daemon"
${RUN_AS_SUDO} mkdir -p /etc/docker
if [[ -f /etc/docker/daemon.json ]]; then
    ${RUN_AS_SUDO} cp /etc/docker/daemon.json /etc/docker/daemon.json.bak
    log "  a daemon.json already existed; it was backed up to daemon.json.bak"
fi
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "live-restore": true
}
EOF

if [[ "${SKIP_DOCKER_RESTART}" -eq 1 ]]; then
    log "  daemon.json written, Docker was not restarted"
    log "  new containers get the log limits straight away; the running"
    log "  ones need a restart, and live-restore needs one too:"
    log "    sudo systemctl restart docker"
else
    log "  restarting Docker to apply the new settings (live-restore keeps"
    log "  the running containers up, so nothing is interrupted)"
    ${RUN_AS_SUDO} systemctl restart docker
    log "  container logs are capped at 10 MB x 3 files each"
fi

# ---------------------------------------------------------------------
# Housekeeping
#
# Docker keeps every image it has ever pulled. On a 1 TB disk that is
# not a shortage, but it is untidy, and the images of a stack that has
# been redeployed a dozen times are the ones that are never used again.
# ---------------------------------------------------------------------

log "installing the weekly Docker cleanup"
cat > /etc/cron.d/spn-docker-cleanup <<'EOF'
# Removes the images and the stopped containers that nothing uses. The
# minute is 23 so it does not collide with everything else that runs on
# the hour.
23 4 * * 0 root /usr/bin/docker image prune -f --filter "until=168h" >/dev/null 2>&1
23 4 * * 0 root /usr/bin/docker container prune -f --filter "until=168h" >/dev/null 2>&1
EOF
chmod 644 /etc/cron.d/spn-docker-cleanup

# ---------------------------------------------------------------------
# Firewall (opt in)
# ---------------------------------------------------------------------

if [[ "${FIREWALL}" -eq 1 ]]; then
    log "installing ufw"
    ${RUN_AS_SUDO} apt-get install -y -qq ufw >/dev/null
    ${RUN_AS_SUDO} ufw allow OpenSSH >/dev/null
    ${RUN_AS_SUDO} ufw --force enable >/dev/null
    log "  only SSH is allowed in"
    warn "CasaOS talks to its own services over the LAN interface. If the"
    warn "panel stops working, 'sudo ufw disable' puts it back."
else
    log "not touching the firewall (pass --firewall to install ufw)"
fi

# ---------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------

log ""
log "the host is ready. Next:"
log "  1. copy the project to /opt/spn and fill in .env (docs/DEPLOY_HOME.md)"
log "  2. docker compose -f docker-compose.prod.yml -f docker-compose.home.yml up -d"
log "  3. check https://<your hostname>/readyz"
