# Putting this site on entrosana.com

Until the cutover, entrosana.com is WordPress (Docker on e14, `127.0.0.1:8090`). This site replaces it behind the **same Cloudflare tunnel**. Nothing changes in DNS: both zones are on Cloudflare, and the tunnel already carries entrosana.com. entrosana.app is untouched, apart from the short tunnel restart.

## Before the cutover

- [ ] This branch is merged into `master`.
- [ ] `src/legal/privacy.en.html` and `privacy.de.html` say what is true on the day. (In this branch the backup copy is at Proton Drive in both languages; the live German page on WordPress still names Cloudflare R2.)
- [ ] Contact forms: decide on `PUBLIC_CONTACT_ENDPOINT` (see the README). Without it, the request forms open the visitor's mail app with the message filled in. The WordPress contact endpoint goes away with WordPress.
- [ ] `public/wp-content/uploads/` holds every WordPress file that is linked from elsewhere; entrosana.app links six (Value System slides and worksheets, the GPU deck). Copy in anything newer first.

## Build and start on e14

```sh
cd ~/entrosana-site
git pull
pnpm install --frozen-lockfile
pnpm build
cp deploy/entrosana-site.service ~/.config/systemd/user/   # first time only
systemctl --user daemon-reload
systemctl --user enable --now entrosana-site.service      # later builds: systemctl --user restart entrosana-site
```

sirv reads `dist/` once at start, so every new build needs that restart. Check locally before switching anything:

```sh
curl -s  http://127.0.0.1:4321/healthz                                                    # ok
curl -sI -H 'Host: entrosana.com' -H 'X-Forwarded-Proto: https' http://127.0.0.1:4321/    # 200, security headers, HSTS
curl -sI -H 'Host: www.entrosana.com' http://127.0.0.1:4321/hub/                          # 301 to https://entrosana.com/hub/
curl -sI http://127.0.0.1:4321/wp-content/uploads/2026/08/value-system-slides-en.pdf      # 200
```

## Switch the tunnel

In the cloudflared configuration on e14 (`~/.cloudflared/config.yml`), the ingress rules for `entrosana.com` and `www.entrosana.com` point at WordPress, `http://127.0.0.1:8090`. Point both at `http://127.0.0.1:4321`. Keep `/api/.+` and entrosana.app as they are. Then validate and restart the tunnel service (`entrosana-tunnel`):

```sh
cloudflared tunnel ingress validate
```

One cloudflared process serves both domains, so entrosana.app drops for about a second during the restart.

From outside, check `https://entrosana.com/` (200, `content-security-policy: frame-ancestors 'none'; …`), `https://www.entrosana.com/` (301), one of the PDFs above, and `https://entrosana.com/wp-sitemap.xml` (301 to `/sitemap.xml`). In Google Search Console, submit `https://entrosana.com/sitemap.xml`.

## Roll back

Point the two ingress rules back at `http://127.0.0.1:8090` and restart the tunnel. Leave the WordPress containers running until the new site has carried the domain for a while.

## Afterwards

- The LAN edge (`entrosana-edge`, Caddy) is gone from this repository. It was bound to 192.168.105.119, an address e14 no longer has, and was crash-looping. If its unit still exists on e14: `systemctl --user disable --now entrosana-edge.service`.
- The Tailscale Funnel root keeps pointing at `127.0.0.1:4321` and so shows the same site.
- GitHub Pages builds every push to `master` under `giansn.github.io/entrosana-site/`, with the base path and `noindex`, as a preview copy.
