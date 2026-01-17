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
| Machine | q35 (for PCI passthrough) |
| GPU | Intel UHD 770 (iGPU passthrough) |

## Hardware Transcoding

Intel iGPU is passed through to the VM for hardware-accelerated transcoding.

| Component | Details |
|-----------|---------|
| GPU | Intel UHD 770 (AlderLake-S GT1) |
| PCI Address | 0000:00:02.0 |
| Driver | i915 |
| VA-API | Intel iHD driver 23.1.1 |
| Kernel | 6.1.0-42-amd64 (standard, not cloud) |

### Supported Codecs

| Codec | Decode | Encode |
|-------|--------|--------|
| H.264 | Yes | Yes |
| HEVC/H.265 | Yes | Yes |
| VP9 | Yes | No |
| AV1 | Yes | No |

### Plex Settings

Hardware transcoding is enabled in Preferences.xml:
- `HardwareAcceleratedCodecs="1"` - Hardware decode
- `HardwareAcceleratedEncoders="1"` - Hardware encode

### Monitoring GPU Usage

```bash
# Real-time GPU monitor
sudo intel_gpu_top

# Check VA-API capabilities
vainfo --display drm --device /dev/dri/renderD128

# Verify Plex transcode session (look for transcodeHw fields)
curl -s "http://localhost:32400/status/sessions?X-Plex-Token=<token>"
```

### Required Packages

- `intel-media-va-driver-non-free` - Intel VA-API driver
- `intel-gpu-tools` - GPU monitoring tools
- `linux-image-amd64` - Standard kernel (not cloud) with i915 driver

## Endpoints

| Service | URL |
|---------|-----|
| Web UI | https://192.168.7.5:32400/web |
| API | https://192.168.7.5:32400 |

## Media Storage

Media files are stored on PVE host (cold8tb ZFS pool) and mounted via NFS.

| Component | Value |
|-----------|-------|
| ZFS Dataset | cold8tb/media |
| PVE Path | /srv/aso/media |
| Capacity | 7.1 TB |
| Type | HDD (cold storage) |
| NFS Export | 192.168.5.215:/srv/aso/media |
| Plex Mount | /media |

### Directory Structure

| Plex Mount | PVE Path | Contents |
|------------|----------|----------|
| /media/movies | /srv/aso/media/movies | Movies |
| /media/tv | /srv/aso/media/tv | TV Shows |
| /media/music | /srv/aso/media/music | Music |

### Adding Media

```bash
# On PVE host - Movies (use "Movie Name (Year)" format)
/srv/aso/media/movies/Movie Name (2024)/Movie Name (2024).mkv

# On PVE host - TV Shows (use "Show Name/Season X" format)
/srv/aso/media/tv/Show Name/Season 1/Show Name - S01E01.mkv
```

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

## Monitoring

Plex metrics are exported to Prometheus and visible in Grafana.

| Component | Value |
|-----------|-------|
| Exporter | /usr/local/bin/plex_exporter.py |
| Port | 9595 |
| Service | plex-exporter.service |
| Grafana Dashboard | Plex Media Server |

### Metrics

| Metric | Description |
|--------|-------------|
| plex_up | Server availability |
| plex_sessions_total | Active sessions |
| plex_transcodes_total | Active transcodes |
| plex_transcode_hw_decode | HW decode sessions |
| plex_transcode_hw_encode | HW encode sessions |
| plex_library_size | Items per library |
| plex_bandwidth_total_kbps | Total bandwidth |

## Dependencies

- NFS share from PVE host (192.168.5.215:/srv/aso/media)
- DHCP reservation for 192.168.7.5
- Prometheus (VM 130) for metrics scraping

## Setup Date

2026-01-17
