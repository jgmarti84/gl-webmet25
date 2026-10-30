# OPERATIONS.md — WebMet25 Operational Reference

> Covers disk management, product deletion, and other operational tasks that don't belong in the data-flow or component documentation.

---

## 1. ProductDeleter — Bulk Disk + DB Cleanup

**File:** [`indexer/indexer/deleter.py`](../indexer/indexer/deleter.py)  
**CLI wrapper:** [`scripts/delete_products.sh`](../scripts/delete_products.sh)

`ProductDeleter` deletes COG files from disk **and** their corresponding `RadarCOG` records from the database in a single transaction. Use it for routine retention management or emergency disk-space recovery.

### 1.1 What it Does

1. Scans `ROOT_RADAR_PRODUCTS_PATH` for `.tif` files matching the given criteria (date, radar codes, product keys)
2. Deletes matching files from disk; removes empty parent directories
3. Deletes matching `RadarCOG` records from the database in one transaction
4. Optionally deletes `genpro25.log.YYYY-MM-DD` log files from `LOGS_PATH`

### 1.2 Running the Deleter

```bash
# From inside the indexer container:
docker exec radar_indexer python -m indexer.deleter \
    --date 2026-04-01 \
    --radar-codes RMA1,AR5 \
    --product-keys DBZHo,COLMAXo

# Dry run (shows what would be deleted without deleting):
docker exec radar_indexer python -m indexer.deleter \
    --date 2026-04-01 \
    --dry-run

# Delete all products for a specific date across all radars:
docker exec radar_indexer python -m indexer.deleter --date 2026-04-01
```

### 1.3 Safety Notes

- Always run `--dry-run` first to verify scope before a destructive delete
- The DB delete is transactional — if the transaction fails, the filesystem deletions already made are **not** rolled back. Prefer running during low-activity periods
- `is_active` on Radar is recalculated on the next COGWatcher scan after deletion

---

## 2. Docker Disk Management

Reference commands for Docker/containerd disk cleanup. See also [`scripts/MANAGE_COMMANDS.md`](../scripts/MANAGE_COMMANDS.md).

### 2.1 Check Disk Usage

```bash
# Docker layer + volume summary
docker system df

# Detailed breakdown
docker system df -v
```

### 2.2 Prune Unused Resources

```bash
# Remove stopped containers, dangling images, unused networks (safe)
docker system prune

# Also remove unused volumes and all untagged images (destructive!)
docker system prune -a --volumes
```

### 2.3 Selective Pruning

```bash
# Prune only unused images (keeps ones used by running containers)
docker image prune -a

# Prune only volumes not attached to a running container
docker volume prune

# Remove a specific volume (destructive!)
docker volume rm webmet25_radar_db_data
```

### 2.4 containerd Snapshot Cleanup (WSL2 / Rancher Desktop)

If using containerd as the Docker runtime (Rancher Desktop on WSL2):

```bash
# List containerd namespaces
sudo ctr namespaces list

# Compact unused snapshots in the moby namespace
sudo ctr -n moby snapshots rm $(sudo ctr -n moby snapshots list -q)
```

### 2.5 Journal Log Vacuuming (WSL2)

```bash
# Show journal disk usage
journalctl --disk-usage

# Vacuum logs older than 7 days
sudo journalctl --vacuum-time=7d

# Vacuum to a size limit
sudo journalctl --vacuum-size=100M
```

---

## 3. Database Maintenance

### 3.1 Manual COG Record Cleanup

```bash
# Open an interactive DB shell
docker compose exec db-init python -m radar_db.manage shell

# Delete MISSING records older than 30 days
from datetime import datetime, timedelta
cutoff = datetime.utcnow() - timedelta(days=30)
deleted = session.query(RadarCOG).filter(
    RadarCOG.status == COGStatus.MISSING,
    RadarCOG.updated_at < cutoff
).delete()
session.commit()
print(f"Deleted {deleted} records")
```

### 3.2 Check Database State

```bash
# Row counts, active radars, recent COGs
docker compose exec db-init python -m radar_db.manage info

# Check migration status
docker compose exec db-init python -m radar_db.manage migrate current
```

### 3.3 Full Development Reset

```bash
# Drop all tables + recreate + reseed (development only — destroys all indexed data)
docker compose exec db-init python -m radar_db.manage reset --force --seed
```

---

## 4. Indexer — Missing-File Check

The indexer continuously reconciles the database against the filesystem to mark records for files that have been deleted from disk as `MISSING`. Two watchers use different strategies optimised for their respective corpus sizes.

### 4.1 How each watcher works

| Watcher | Strategy | Trigger | Cost per cycle |
|---|---|---|---|
| **COGWatcher** | Chunked cursor scan — checks `MISSING_CHECK_BATCH_SIZE` records per cycle, ordered by `id`, advancing a cursor | Every scan cycle (30 s) | ~1 s (1 000 `Path.exists()` calls) |
| **TopsAndCoresWatcher** | Full time-windowed scan — queries all `AVAILABLE` records within the retention window | Every 20 cycles (~10 min) | ~14 s (≈13 500 records at 45 days) |

The COG cursor resets to 0 when it reaches the end of the retention window, starting the next pass from the oldest record in the window. A full pass over 45 days of COG records takes approximately 31 hours at default batch size.

### 4.2 Environment variables

| Variable | Default | Description |
|---|---|---|
| `MARK_MISSING_FILES` | `true` | Master on/off switch for both checks |
| `MISSING_CHECK_DAYS` | `45` | Retention window in days. Set to ≥ the longest retention period across all radars. Changing this does not require a schema migration. |
| `MISSING_CHECK_BATCH_SIZE` | `1000` | Records per COG cursor batch. Increase to shorten the full-pass duration; decrease to reduce per-cycle overhead. |

### 4.3 Log patterns

```
# COG: files marked missing in a batch (only logged when count > 0)
Marked N COG file(s) as missing (cursor=12345678)

# COG: individual file marked missing
WARNING - Marked as missing: RMA5/2026/09/07/RMA5_0315_01_...tif

# TopsAndCores: triggered every 20 cycles
WARNING - TOPS_CORES marked as missing: /mnt/.../RMA15_..._TOPS_CORES.geojson
```

### 4.4 Tuning guidance

- **Cursor too slow** (stale MISSING records taking too long to be detected): increase `MISSING_CHECK_BATCH_SIZE` to e.g. `5000`. Each cycle will take ~5 s instead of ~1 s, reducing full-pass time to ~6 hours.
- **Extending retention in radarlib**: update `MISSING_CHECK_DAYS` to match the new maximum retention before the change takes effect, so no files fall outside the check window.
- **Disabling entirely**: set `MARK_MISSING_FILES=false`. Useful during planned maintenance that involves bulk file deletion, to avoid a flood of MISSING records before the DB is also updated.

---

## 6. Indexer Health Checks

```bash
# View real-time indexer logs
docker compose logs -f indexer

# Check if indexer is processing files (look for "Indexed COG" log lines)
docker compose logs --tail=50 indexer

# Verify the watch path is mounted and has files
docker exec radar_indexer ls -la /product_output/

# Run a single scan manually (one-shot, useful for debugging)
docker exec radar_indexer python -m indexer.main --single --debug

# Check DB connection from indexer
docker exec radar_indexer python -m indexer.manage check
```

---

## 7. API Health & Cache

```bash
# Health check
curl http://localhost/api/v1/health

# View frame/tile cache statistics (L1 LRU + L2 Redis)
curl http://localhost/api/v1/tiles/cache/stats

# Flush the colormap in-process cache. Requires an admin session (the admin panel and
# scripts/import_colormap.py already do this for you); with curl, log in first:
curl -c cj.txt -X POST http://localhost/api/v1/auth/login -H "Content-Type: application/json" -d '{"username":"<admin>","password":"<password>"}'
curl -b cj.txt -X POST http://localhost/api/v1/colormap/cache/invalidate
```

## 8. User Management

Run these from the repo root (`gl-webmet25`). They use the `db-init` image, so no extra setup is needed.

```bash
# Create an admin (prompts for the password twice, nothing is echoed)
make create-admin U=maria

# Set a new password for any user and close all their sessions
make reset-password U=maria
```

- The **first admin** is created automatically by `db-init` from `ADMIN_USERNAME` / `ADMIN_PASSWORD` when there are no users. After the first start, run `make reset-password U=<that user>` and remove both variables from `.env`.
- An admin **cannot reset their own password from the panel**; use `make reset-password` on the server.
- Nobody can use the site without an account. The admin creates accounts from the panel; people can also create their own when public sign-up is on (see [§9](#9-public-registration-and-e-mail)). A mail entered by an admin counts as verified.
- Other users are managed from the admin panel (**Usuarios**): create, change role, activate/deactivate, reset password, close sessions. Users are never deleted, only deactivated.
- If a user is locked out after 5 failed logins, they can try again after 15 minutes, or an admin can reset their password.
- Session lifetimes and the lockout are set from `.env` (`ACCESS_TOKEN_TTL_MINUTES`, `SESSION_IDLE_TTL_HOURS`, `SESSION_ABSOLUTE_TTL_DAYS`, `LOGIN_MAX_FAILED_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`; defaults in [`DATA_FLOW.md`](DATA_FLOW.md)). Recreate the API afterwards with `make api`. Sessions already issued keep the lifetime they were created with.
- If the API starts with no active admin it logs a warning with the command to create one.

## 9. Public Registration and E-mail

**What it does.** Anyone can create a `viewer` account at `/register` (username, mail, password, acceptance of the terms). The account cannot log in until the person opens the one-time link sent to the mail (valid 24 h). People log in with their username or their mail, and recover a forgotten password at `/forgot` (link valid 60 min; resetting closes every open session and lifts a lockout). It is **off by default**.

### 9.1 Settings

All go in `.env` (commented in `.env.example`); docker compose passes them to the API with these defaults. Recreate the API afterwards with `make api`.

| Variable | Default | Meaning |
|----------|---------|---------|
| `REGISTRATION_ENABLED` | `false` | Master switch of the sign-up |
| `PUBLIC_BASE_URL` | empty | Public address of the site, used in the links of the mails (no trailing slash) |
| `MAIL_HOST` | empty | SMTP server |
| `MAIL_PORT` | `587` | SMTP port (usually 587 with STARTTLS, 465 with SSL) |
| `MAIL_USER` / `MAIL_PASSWORD` | empty | SMTP login; leave `MAIL_USER` empty for a server that needs none |
| `MAIL_FROM` | empty | Sender address |
| `MAIL_STARTTLS` | `true` | Encrypt the connection by upgrading it (port 587). Ignored when `MAIL_USE_SSL` is on |
| `MAIL_USE_SSL` | `false` | Encrypted from the first byte (port 465) |
| `TERMS_REQUIRED` | `false` | Ask the person to accept the terms and the privacy policy in the sign-up (checkbox and links). Off by default: the form shows neither. Turn it on before opening the sign-up to the public (see §9.3) |
| `TERMS_URL` / `PRIVACY_URL` | empty | Links shown in the sign-up form when `TERMS_REQUIRED=true`; the texts are provided by the observatory |
| `EMAIL_VERIFY_TTL_HOURS` | `24` | Life of the verification link. A pending account can only be replaced by a new sign-up after this time |
| `PASSWORD_RESET_TTL_MINUTES` | `60` | Life of the reset link |
| `MAIL_MAX_PER_HOUR` | `3` | Mails one account may receive per hour (all kinds count) |
| `MAIL_MIN_INTERVAL_SECONDS` | `60` | Minimum time between two mails to one account |
| `MAIL_MAX_GLOBAL_PER_HOUR` | `200` | Mails of the whole site per hour; past it only password recovery goes out |
| `MAIL_MAX_GLOBAL_PER_DAY` | `1500` | Mails of the whole site per day; keep it under the SMTP provider's daily limit (Gmail Workspace: about 2,000) |

When a cap stops a mail, the API sends nothing and answers exactly as if it had, so the answer never reveals whether an account exists.

### 9.2 When it is available

- **Sign-up** needs `REGISTRATION_ENABLED=true` **and** `MAIL_HOST`, `MAIL_FROM` and `PUBLIC_BASE_URL`; only with `TERMS_REQUIRED=true` it also needs `TERMS_URL` and `PRIVACY_URL`.
- **Verification and password recovery** only need the mail settings (`MAIL_HOST`, `MAIL_FROM`, `PUBLIC_BASE_URL`).
- If `REGISTRATION_ENABLED=true` but something is missing, the API says what in its log at startup and the sign-up stays off (the endpoint answers 503 and the login does not offer "Crear cuenta").

### 9.3 Turning it on in production

1. If a proxy sits in front of nginx, configure `set_real_ip_from` / `real_ip_header` first. The limits of these endpoints (10 requests/minute per IP) are per client IP: without the real IP every visitor shares the proxy's and the quota runs out for everybody.
2. Set SPF and DKIM for the sender domain, or the mails land in spam.
3. Gmail / Workspace: use an app password (not the account password) and mind the daily caps (about 500 and 2,000 mails).
4. Get the terms and the privacy policy (the texts come from the observatory, ideally reviewed by its legal area), put their addresses in `TERMS_URL` and `PRIVACY_URL` and set `TERMS_REQUIRED=true`. It is off by default so the sign-up can be tried before the texts exist, but **before opening it to the public** the people must be shown them: it is the information and consent notice that the data protection law (Ley 25.326) expects when personal data is collected. While it is off the API warns about it in its log at startup, and no acceptance is recorded (`terms_accepted_at` stays empty).
5. Fill `MAIL_*`, `PUBLIC_BASE_URL` and set `REGISTRATION_ENABLED=true`, then deploy with `make up` (or `make db-init` and `make api`). `db-init` applies the pending database migration; it fails with a clear message, listing them, if two users have the same mail. Fix those rows and run it again.
6. To turn it off at once: `REGISTRATION_ENABLED=false` and `make api`. Accounts already created keep working.

### 9.4 Development

The development stack has a local mailbox, **Mailpit**: `http://localhost:8025` (reachable from this machine only). The main API of that stack already has sign-up on and sends there, so nothing leaves your computer. The black-box and end-to-end tests use their own API (`api-e2e`) with the same mailbox; see [`E2E_TESTING.md`](E2E_TESTING.md).

### 9.5 Known gap

There is **no automatic cleanup** of unverified accounts or of expired rows in `email_tokens`. An unverified account is replaced when someone signs up again with its username or mail after its link expired (24 h), and until then it keeps that username. Expired tokens pile up until a cleanup job is written. (Old logins in `user_sessions` are purged on each login of that user; see §8.)

### 9.6 Sign in with Google

**What it does.** The login page shows a "Continuar con Google" button when `GOOGLE_CLIENT_ID` is set. Anyone with a Google account can enter: if there is a user with that mail (or already linked to that Google account) they enter; otherwise a `viewer` account is created for them, with the mail already verified (Google confirmed it) and no form. It is **not** tied to `REGISTRATION_ENABLED`: with the client ID set it is always on, so the site is open to every Google account. Administrators never enter this way (they use user and password), deactivated accounts do not either, and a mail already linked to another Google account is refused.

- **Setting:** `GOOGLE_CLIENT_ID` in `.env` (public, not a secret; no client secret is used). Recreate the API with `make api`. Empty = off: the button is not shown and `POST /auth/google` answers 503.
- **Google Cloud console:** create a project, set up the consent screen (type **External**, then **publish** the app: in "Testing" only the listed test users can enter), and create an OAuth client ID of type **Web application** with the site addresses as "Authorized JavaScript origins" (the same as `ALLOWED_ORIGINS`; add the public domain when the site has one). No redirect URIs are needed.
- **Account linking:** the first time, an existing account with the same mail is linked to the Google account (`users.google_sub`) and its mail is marked verified. If that account was never verified (someone signed up with the mail and chose a password), its password is dropped and its sessions closed, since the person who set it never owned the mailbox. Later logins find the account by the Google id, even if the mail changed.
- **Network:** the API downloads Google's public keys over HTTPS (`https://www.googleapis.com/oauth2/v3/certs`) to check each token's signature; they are kept in memory for an hour. The visitor's browser must be able to reach `accounts.google.com`.
- **Legal:** a Google sign-up records no acceptance of the terms (`terms_accepted_at` stays empty). Before opening the site to the public, see §9.3 point 4.

---

## 10. Serving a Copy Under a Base Path

When two copies of the site must share one hostname (for example on stage, Javi's copy at `/` and Nacho's at
`/nacho/`), the proxy in front routes by prefix and **strips** it. Nothing in the image changes; the copy learns its
prefix from the `X-Forwarded-Prefix` header (see `docs/DATA_FLOW.md`, "Base path").

Caddyfile of the proxy (stage: `webmet_caddy`, block `:8080`):

```
:8080 {
  bind 127.0.0.1
  encode zstd gzip

  # The copy under /nacho/: strip the prefix and tell its nginx about it.
  redir /nacho /nacho/
  handle_path /nacho/* {
    reverse_proxy 127.0.0.1:8081 {
      header_up X-Forwarded-Prefix /nacho
    }
  }

  # Everything else: the copy at the root. A client cannot fake a prefix here.
  handle {
    request_header -X-Forwarded-Prefix
    reverse_proxy 127.0.0.1:80
  }
}
```

With `admin off`, apply it with `docker restart <caddy container>` (`caddy reload` needs the admin API).

In the `.env` of the copy under the prefix:

- `FRONTEND_PORT` = the port the Caddyfile points at (`8081` above).
- `PUBLIC_BASE_URL=https://<host>/nacho`, so the links in the mails carry the prefix.
- `ALLOWED_ORIGINS` = the same public origin as the other copy (`https://<host>`): the origin has no path.

Each copy keeps its own sessions (cookie names carry the prefix), so one browser can be logged in to both.

---

**Document Version:** 1.3.0  
**Last Updated:** October 27, 2026
