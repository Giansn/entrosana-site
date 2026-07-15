# GoDaddy DNS cutover — entrosana.com → GitHub Pages

**Do not touch:** MX, TXT (ProtonMail), or any non-web records.
**Safe:** replace the apex **A** that currently points at dead EC2 web (`3.64.28.14`). The EC2 EIP can keep existing for SSH/other; only DNS changes.

## Records to set (DNS Management for entrosana.com)

Delete apex A `3.64.28.14` if present, then add:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | @ | 185.199.108.153 | 600 |
| A | @ | 185.199.109.153 | 600 |
| A | @ | 185.199.110.153 | 600 |
| A | @ | 185.199.111.153 | 600 |
| CNAME | www | giansn.github.io | 600 |

## After save
1. Wait 5–30 min (sometimes up to a few hours).
2. Check: https://github.com/Giansn/entrosana-site/settings/pages — domain should show verified + HTTPS.
3. From outside: `curl -I https://entrosana.com/`
4. e14 Funnel preview still: `https://e14-1.tailff64b5.ts.net/`

## Rollback
Restore apex A to `3.64.28.14` (or previous value). Pages stay as backup at https://giansn.github.io/entrosana-site/
