#!/usr/bin/env bash
# One-time hardening + Docker install for a FRESH Ubuntu 24.04 LTS server. Run as root:
#
#   sudo bash setup-ubuntu.sh rlm /root/deploy_key.pub
#     $1  deploy user to create (default: rlm)
#     $2  path to the deploy user's SSH PUBLIC key (required)
#
# Safe to re-run. Keep your current SSH session open until you have confirmed that
#   ssh rlm@SERVER   works with the key, because password and root logins are switched off.
set -Eeuo pipefail

DEPLOY_USER="${1:-rlm}"
PUBKEY_FILE="${2:?usage: setup-ubuntu.sh <deploy-user> <ssh-public-key-file>}"
APP_DIR=/srv/rlm

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
grep -q 'Ubuntu 24.04' /etc/os-release || echo "WARNING: written for Ubuntu 24.04; continuing" >&2
grep -Eq '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-) ' "$PUBKEY_FILE" || { echo "$PUBKEY_FILE is not an SSH public key" >&2; exit 1; }

log() { printf '\n== %s\n' "$*"; }

log "system updates and base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get -y -q upgrade
apt-get -y -q install ca-certificates curl gnupg git ufw fail2ban unattended-upgrades
timedatectl set-ntp true || true

log "deploy user '$DEPLOY_USER' with key-only SSH access"
id "$DEPLOY_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$DEPLOY_USER"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$PUBKEY_FILE" "/home/$DEPLOY_USER/.ssh/authorized_keys"
usermod -aG sudo "$DEPLOY_USER"
echo "NOTE: set a sudo password for $DEPLOY_USER with:  passwd $DEPLOY_USER"

log "SSH hardening"
cat > /etc/ssh/sshd_config.d/60-rlm-hardening.conf <<CONF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
AllowUsers $DEPLOY_USER
CONF
sshd -t                      # refuse to continue with a broken config
systemctl reload ssh

log "firewall: only SSH, HTTP and HTTPS"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

log "fail2ban for SSH"
cat > /etc/fail2ban/jail.d/rlm.local <<'CONF'
[sshd]
enabled  = true
maxretry = 5
findtime = 10m
bantime  = 1h
CONF
systemctl enable --now fail2ban
systemctl restart fail2ban

log "automatic security updates"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
cat > /etc/apt/apt.conf.d/52rlm-unattended <<'CONF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:30";
CONF

log "Docker Engine (official repository)"
if ! command -v docker >/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -q
    apt-get -y -q install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
cat > /etc/docker/daemon.json <<'CONF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" },
  "no-new-privileges": true,
  "live-restore": true
}
CONF
systemctl restart docker
# Membership of the docker group is root-equivalent: only the deploy user gets it.
usermod -aG docker "$DEPLOY_USER"

log "application directories"
install -d -m 750 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
install -d -m 700 -o 10001 -g 10001 "$APP_DIR/backups"   # written by the backup container (uid 10001)

log "nightly encrypted backup at 02:30 server time"
cat > /etc/cron.d/rlm-backup <<CONF
30 2 * * * $DEPLOY_USER cd $APP_DIR && docker compose -f docker-compose.prod.yml run --rm backup >> /var/log/rlm-backup.log 2>&1
CONF
touch /var/log/rlm-backup.log && chown "$DEPLOY_USER" /var/log/rlm-backup.log

log "done"
cat <<MSG
Next steps (docs/DEPLOYMENT.md):
  1. In a NEW terminal, confirm:  ssh $DEPLOY_USER@<server>   (key login works) before closing this session.
  2. As $DEPLOY_USER:  git clone <repo> $APP_DIR  (the directory exists and is empty)
  3. cp .env.production.example .env && chmod 600 .env, fill it in, then scripts/deploy.sh --no-pull
MSG
