# Plex Media Server

Plex Media Server for streaming movies, TV shows, and music.

## Infrastructure

| Component | Value |
|-----------|-------|
| VM ID | 150 |
| Hostname | plex |
| IP | 192.168.7.5 |
| OS | Debian 12 |
| CPU | 4 cores |
| RAM | 8 GB |
| Disk | 64 GB (fast-vm SSD) |
| Storage | fast-vm (SSD) |

## Endpoints

| Service | URL |
|---------|-----|
| Web UI | https://192.168.7.5:32400/web |
| API | https://192.168.7.5:32400 |

## Media Storage

Media files are stored on PVE host and mounted via NFS:

| Mount | Source | Contents |
|-------|--------|----------|
| /media/movies | 192.168.5.215:/srv/aso/media/movies | Movies |
| /media/tv | 192.168.5.215:/srv/aso/media/tv | TV Shows |
| /media/music | 192.168.5.215:/srv/aso/media/music | Music |

## Security

- **Firewall (UFW)**: Deny all, allow SSH (22) + Plex (32400)
- **SSH**: Key-only auth, password disabled, root login disabled
- **Fail2ban**: SSH protection (3 attempts = 24h ban)
- **Updates**: Automatic security updates enabled

## Management

```bash
# SSH access
ssh jurgen@192.168.7.5

# Restart Plex
sudo systemctl restart plexmediaserver

# Check status
sudo systemctl status plexmediaserver

# View logs
sudo journalctl -u plexmediaserver -f

# Firewall status
sudo ufw status

# Fail2ban status
sudo fail2ban-client status sshd
```

## Dependencies

- NFS share from PVE host (192.168.5.215:/srv/aso/media)
- DHCP reservation for 192.168.7.5

## Setup Date

2026-01-17
