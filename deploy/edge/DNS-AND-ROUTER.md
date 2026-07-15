# entrosana.com on e14 (EC2 off)

| Piece | Status |
|-------|--------|
| Origin | `entrosana-site.service` → `127.0.0.1:4321` **running** |
| TLS edge | docker `entrosana-edge` (Caddy, host net) on **`192.168.105.119:443`** → 4321 **running** |
| Funnel | `https://e14-1.tailff64b5.ts.net/` → same origin **unchanged** |
| Nextcloud | host `:80` **unchanged** |
| Cert now | self-signed in `deploy/edge/certs/` (browsers warn until LE) |

## Local verify (works today)

```bash
curl -skI --resolve entrosana.com:443:192.168.105.119 https://entrosana.com/
# → 200, title entrosana
```

## Public internet (needs you once)

### 1) GoDaddy DNS — keep ProtonMail MX/TXT

Delete apex **A 3.64.28.14**. Set:

| Type | Name | Value |
|------|------|--------|
| A | @ | **194.230.147.22** (e14 public — `curl -s https://api.ipify.org`) |
| A | www | **194.230.147.22** |

### 2) Ubiquiti port forward

| WAN | → LAN |
|-----|--------|
| TCP **443** | **192.168.105.119:443** |

No port 80 forward (Nextcloud).

### 3) Real Let’s Encrypt (optional, after 1+2)

Replace self-signed in `Caddyfile` with auto HTTPS, recreate container. See comments in Caddyfile.

## Unbound (LAN)

Source points entrosana.com → `192.168.105.119`. Apply: `sudo ~/sygnif/e14-dns/setup.sh`

## Rollback

```bash
systemctl --user disable --now entrosana-edge.service
cd ~/entrosana-site/deploy/edge && docker compose down
```
