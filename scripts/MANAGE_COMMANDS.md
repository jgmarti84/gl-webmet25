## Clean Up Docker/Containerd Resources
Most impactful — prune everything unused:

```bash
docker system prune -a --volumes
```
⚠️ This removes all stopped containers, unused images, networks, and volumes. Use with caution in production.

Or do it selectively:

```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove unused build cache
docker builder prune -a
```

## Check What's Taking Up Space
```bash
# Check Docker's disk usage breakdown
docker system df

# Check what's in containerd's directory
sudo du -sh /var/lib/containerd/*

# General disk usage by directory
sudo du -sh /* 2>/dev/null | sort -rh | head -20
```

## Clean Up Containerd Snapshots Directly
If Docker prune isn't enough:

```bash
sudo systemctl stop containerd
sudo rm -rf /var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/*
sudo systemctl start containerd
```

⚠️ Only do this if you're okay losing all cached layers and containers managed by containerd.

## Check for Large Log Files
System logs can silently eat up disk space:

```bash
# Check journal logs size
journalctl --disk-usage

# Vacuum logs older than 3 days
sudo journalctl --vacuum-time=3d

# Check docker container logs
sudo du -sh /var/lib/docker/containers/*/*-json.log | sort -rh | head -10
```