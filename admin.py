#!/usr/bin/env python3
# entrosana-admin: tailnet-only write-in editor for the live site (dist/) + backend files.
# stdlib only. Visual mode = designMode over the real page (scripts stripped while editing,
# re-attached on save). Raw mode = textarea for allowlisted files. Backups on every save.
# Stamps: sha256 seals are recomputed server-side on save so they stay REAL.
import hashlib, hmac, html, ipaddress, json, os, re, secrets, shutil, subprocess, time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HOME = Path.home()
SITE = HOME / "entrosana-site"
DIST = SITE / "dist"
BACKUPS = SITE / "dist-backups"
# Die Gestaltung wirkt auf das ausgelieferte Theme von entrosana.com, nicht
# mehr auf die statische Fassung. Eigener Sicherungsordner, damit die
# Kopien nicht im Git-Baum von ~/entrosana-wp landen.
WP_THEME = HOME / "entrosana-wp" / "theme" / "entrosana"
WP_BACKUPS = SITE / "wp-backups"
TOKEN_FILE = HOME / ".config" / "entrosana-admin.token"
PORT = 8393

BACKUPS.mkdir(exist_ok=True)
TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
# Guard on CONTENT, not just existence: a 0-byte/whitespace token file (partial
# write, disk-full, manual truncate) must NOT collapse auth to "".
if not TOKEN_FILE.exists() or not TOKEN_FILE.read_text().strip():
    TOKEN_FILE.write_text(secrets.token_urlsafe(16))
    TOKEN_FILE.chmod(0o600)
TOKEN = TOKEN_FILE.read_text().strip()
# Entscheid des Eigentümers, 2026-09-08: im Tailnet reicht das Tailnet. _src_ok()
# lässt nur Loopback und 100.64.0.0/10 durch; wer dort ist, hat sich bei Tailscale
# ausgewiesen. Der Schlüssel bleibt als zweiter Weg (Cookie eak) bestehen.
TAILNET_OPEN = True
# Hub-Verwaltung: Konten, Bewerbungen, Anfragen aus dem Dienst api/ (:4324).
API_URL = "http://127.0.0.1:4324"
API_TOKEN_FILE = HOME / ".config" / "entrosana-api.token"
HUB_CONSOLE = "http://100.115.236.97:8396"
if not TOKEN:
    raise SystemExit("entrosana-admin: refusing to start with an empty auth token")

CTYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".svg": "image/svg+xml", ".png": "image/png", ".js": "text/javascript",
          ".mjs": "text/javascript", ".txt": "text/plain; charset=utf-8"}


# Descriptions follow the v3 build promoted on 2026-09-02; dist/ is rebuilt
# from the live site by build-dist.py.
PAGE_META = {
    "index.html": ("Home", "hero, how we work, the Hub and what runs in it, two model layers, where we stand"),
    "service.html": ("Service", "Tools / Modules / Consulting; the tier figure; hosted, hybrid, on-premises"),
    "hub.html": ("Hub", "what the Hub does (market and console), who it's for, an example by role"),
    "modules.html": ("Modules", "module areas under tabs; request and propose, each with its own form"),
    "roadmap.html": ("Roadmap", "what is built, what is not, and in what order; the three decisions"),
    "request-access.html": ("Request access", "pilot form and contact"),
    "imprint.html": ("Imprint", "provider identification (draft)"),
    "privacy.html": ("Privacy", "privacy policy (draft)"),
    "404.html": ("404 page", "shown for unknown URLs"),
}
GROUPS = [
    ("Site sections", ["index.html", "service.html", "hub.html", "modules.html",
                       "roadmap.html", "request-access.html"]),
    ("Legal", ["imprint.html", "privacy.html"]),
    ("System", ["404.html"]),
]


def is_stub(f: Path) -> bool:
    try:
        return 'http-equiv="refresh"' in f.read_text(encoding="utf-8")[:600]
    except Exception:
        return False


def stub_target(f: Path) -> str:
    m = re.search(r'url=([^"\s]+)', f.read_text(encoding="utf-8")[:600])
    return m.group(1) if m else "?"


def dist_bundles():
    """The stylesheets the dist pages actually link, in filename order.

    Read off the pages rather than globbed: build-dist.py emits one bundle
    per enqueue set (site.css, site-home.css, site-tabs.css), and a glob also
    catches leftovers like site.base.css from the old Astro build, which
    nothing links and which would be listed as if it were live.
    """
    found = set()
    for p in DIST.glob("*.html"):
        try:
            head = p.read_text(encoding="utf-8", errors="replace").split("</head>")[0]
        except OSError:
            continue
        for href in _SHEET_RE.findall(head):
            name = href.split("/")[-1]
            if (DIST / "assets" / name).exists():
                found.add(name)
    return sorted(found)


def raw_allowlist():
    files = sorted(f"dist/{p.name}" for p in DIST.glob("*.html"))
    # every bundle in use, not just site.css — the front page and the two tab
    # pages link their own
    files += [f"dist/assets/{n}" for n in dist_bundles()]
    files += ["server.mjs"]
    return files


def resolve_raw(rel):
    if rel not in raw_allowlist():
        return None
    p = (SITE / rel).resolve()
    return p if str(p).startswith(str(SITE)) and p.exists() else None


def backup(p: Path, store: Path = None):
    store = store or BACKUPS
    store.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    dest = store / f"{p.name}.{ts}"
    shutil.copy2(p, dest)
    keep = sorted(store.glob(f"{p.name}.*"))
    for old in keep[:-20]:
        old.unlink()
    return dest.name


def restamp(doc: str) -> str:
    def fix(m):
        digest = hashlib.sha256(m.group(1).encode("utf-8")).hexdigest()
        return f"sha256(“{m.group(1)}”) · <b>{digest[:6]}…{digest[-4:]}</b>"
    return re.sub(r"sha256\(“([^”]+)”\) · <b>[^<]+</b>", fix, doc)


# ── design controls: letter size, colour, container measures ──────────────
# Persisted as a marked, machine-readable override block APPENDED to site.css,
# so it wins over the theme :root (source order) and applies site-wide without
# touching any page. Values are strictly validated before they reach the file.
SITE_CSS = WP_THEME / "assets" / "site.css"
DESIGN_START = "/* === ENTROSANA-DESIGN-OVERRIDES (managed by admin /design; do not hand-edit) === */"
DESIGN_END = "/* === END ENTROSANA-DESIGN-OVERRIDES === */"
DESIGN_DEFAULTS = {
    "seal": "#2BD4E8", "paper": "#1B1E24", "ink": "#E9EBE7",              # dark theme
    "light_seal": "#077183", "light_paper": "#F4F5F3", "light_ink": "#16181D",  # light theme
    "wrap": 1140, "gutter": 3.0, "radius": 4, "size": 100,               # shared
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def read_design():
    v = dict(DESIGN_DEFAULTS)
    try:
        m = re.search(r"/\* @design (\{.*?\}) \*/", SITE_CSS.read_text(encoding="utf-8"))
        if m:
            saved = json.loads(m.group(1))
            for k in v:
                if k in saved:
                    v[k] = saved[k]
    except Exception:
        pass
    return v


def _validate_design(d):
    v = {}
    for k in ("seal", "paper", "ink", "light_seal", "light_paper", "light_ink"):
        c = str(d.get(k, DESIGN_DEFAULTS[k]))
        if not _HEX.match(c):
            raise ValueError(f"{k} must be a #rrggbb colour")
        v[k] = c

    def num(k, lo, hi, cast):
        x = cast(d.get(k, DESIGN_DEFAULTS[k]))
        if not (lo <= x <= hi):
            raise ValueError(f"{k} out of range {lo}..{hi}")
        return x

    v["wrap"] = num("wrap", 800, 1680, int)
    v["gutter"] = round(num("gutter", 0.0, 6.0, float), 2)
    v["radius"] = num("radius", 0, 40, int)
    v["size"] = num("size", 70, 140, int)
    return v


def build_design_css(v):
    # gutter stays a responsive clamp (fixed rem regressed mobile); at the 3.0
    # default this reproduces the base clamp exactly, so save-defaults is a no-op.
    gutter = f"clamp(1.25rem, .8rem + 2.5vw, {v['gutter']}rem)"
    return (DESIGN_START + "\n"
            + "/* @design " + json.dumps(v) + " */\n"
            + ":root{\n"
            + f"  --seal: {v['seal']};\n"
            + f"  --paper: {v['paper']};\n"
            + f"  --ink: {v['ink']};\n"
            + f"  --wrap: {v['wrap']}px;\n"
            + f"  --gutter: {gutter};\n"
            + f"  --radius: {v['radius']}px;\n"
            + f"  font-size: {v['size']}%;\n"
            + "}\n"
            # light theme gets its OWN colours (higher specificity than plain :root,
            # so this is what wins when a visitor toggles light mode).
            + ':root[data-theme="light"]{\n'
            + f"  --seal: {v['light_seal']};\n"
            + f"  --paper: {v['light_paper']};\n"
            + f"  --ink: {v['light_ink']};\n"
            + "}\n"
            + DESIGN_END + "\n")


def write_design(v):
    css = SITE_CSS.read_text(encoding="utf-8")
    i = css.find(DESIGN_START)
    if i != -1:
        j = css.find(DESIGN_END, i)
        if j == -1:
            # missing end marker = corrupt block; fail closed rather than
            # truncate the whole stylesheet (which len(css) would do).
            raise ValueError("site.css override block has no end marker; fix by hand before saving")
        css = css[:i].rstrip() + "\n" + css[j + len(DESIGN_END):].lstrip()
    css = css.rstrip() + "\n\n" + build_design_css(v)
    b = backup(SITE_CSS, WP_BACKUPS)
    SITE_CSS.write_text(css, encoding="utf-8")
    return b


def design_page():
    v = read_design()
    tpl = DESIGN_HTML
    for k, val in v.items():
        tpl = tpl.replace("__%s__" % k.upper(), str(val))
    return tpl


DESIGN_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>entrosana · design</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}
body{margin:0;height:100vh;display:flex;background:#1B1E24;color:#E9EBE7;font-family:Calibri,'Segoe UI',sans-serif}
.panel{width:330px;flex:none;overflow:auto;padding:1.2rem;border-right:1px solid #323843}
.panel h1{font-size:1.15rem;margin:.2rem 0 1rem}
a.back{color:#8F95A1;font-size:.85rem;text-decoration:none}
.grp{margin:1rem 0;border-top:1px solid #2a2f38;padding-top:.85rem}
.grp h2{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:#2BD4E8;margin:0 0 .7rem}
label{display:flex;align-items:center;justify-content:space-between;gap:.6rem;font-size:.85rem;margin:.55rem 0}
.row{display:flex;align-items:center;gap:.55rem;flex:1;justify-content:flex-end}
.v{color:#8F95A1;font-variant-numeric:tabular-nums;min-width:3.6em;text-align:right}
input[type=range]{flex:1;max-width:150px}
input[type=color]{width:46px;height:26px;border:1px solid #4a505c;border-radius:6px;background:none;padding:0;cursor:pointer}
.actions{position:sticky;bottom:-1.2rem;background:#1B1E24;padding:1rem 0 .2rem;margin-top:1rem;border-top:1px solid #323843}
.btn{background:#2BD4E8;color:#071316;border:0;border-radius:999px;padding:.55em 1.3em;font-weight:bold;cursor:pointer}
.btn.ghost{background:none;color:#E9EBE7;border:1px solid #4a505c}
.msg{font-size:.8rem;color:#8F95A1;margin-top:.6rem;min-height:1.2em}
.wrap-pv{flex:1;position:relative;display:flex}
.pv{flex:1;border:0;background:#0d0f13}
.pvbar{position:absolute;top:10px;right:14px;z-index:5}
select{background:#101318;color:#E9EBE7;border:1px solid #323843;border-radius:6px;padding:.3em .5em}
.seg{display:inline-flex;float:right;border:1px solid #4a505c;border-radius:999px;overflow:hidden;text-transform:none}
.seg button{background:none;border:0;color:#8F95A1;font-family:inherit;font-size:.72rem;padding:.25em .85em;cursor:pointer;letter-spacing:0}
.seg button.on{background:#2BD4E8;color:#071316;font-weight:bold}
.hint{color:#8F95A1;font-size:.75rem;margin-top:.5rem}
</style></head><body>
<div class="panel">
<a class="back" href="/">← dashboard</a>
<h1>Design controls</h1>
<div class="grp"><h2>Letter size</h2>
<label>Base text <span class="row"><input id="size" type="range" min="70" max="140" value="__SIZE__"><span class="v" id="size_v"></span></span></label>
</div>
<div class="grp"><h2>Colour <span class="seg" id="modeseg"><button type="button" data-mode="dark" class="on">Dark</button><button type="button" data-mode="light">Light</button></span></h2>
<label>Accent <input id="seal" type="color"></label>
<label>Background <input id="paper" type="color"></label>
<label>Text <input id="ink" type="color"></label>
<div class="hint" id="modehint">editing dark theme · switch to tune light mode</div>
</div>
<div class="grp"><h2>Container measures</h2>
<label>Content width <span class="row"><input id="wrap" type="range" min="800" max="1680" step="10" value="__WRAP__"><span class="v" id="wrap_v"></span></span></label>
<label>Side padding <span class="row"><input id="gutter" type="range" min="0" max="6" step=".25" value="__GUTTER__"><span class="v" id="gutter_v"></span></span></label>
<label>Corner radius <span class="row"><input id="radius" type="range" min="0" max="40" step="1" value="__RADIUS__"><span class="v" id="radius_v"></span></span></label>
</div>
<div class="actions">
<button class="btn" id="save">Save to site</button>
<button class="btn ghost" id="reset">Reset</button>
<div class="msg" id="msg">Drag to preview live · Save writes assets/site.css (with backup)</div>
</div>
</div>
<div class="wrap-pv">
<div class="pvbar"><select id="pgsel">
<option value="index.html">Home</option><option value="service.html">Service</option>
<option value="hub.html">Hub</option><option value="modules.html">Modules</option>
<option value="roadmap.html">Roadmap</option>
<option value="request-access.html">Request access</option></select></div>
<iframe class="pv" id="pv" src="/preview/index.html"></iframe>
</div>
<script>
var D={size:__SIZE__,wrap:__WRAP__,gutter:__GUTTER__,radius:__RADIUS__,
dark:{seal:'__SEAL__',paper:'__PAPER__',ink:'__INK__'},
light:{seal:'__LIGHT_SEAL__',paper:'__LIGHT_PAPER__',ink:'__LIGHT_INK__'}};
var mode='dark';
function loadPickers(){seal.value=D[mode].seal;paper.value=D[mode].paper;ink.value=D[mode].ink;}
function readShared(){D.size=+size.value;D.wrap=+wrap.value;D.gutter=+gutter.value;D.radius=+radius.value;
size_v.textContent=D.size+'%';wrap_v.textContent=D.wrap+'px';gutter_v.textContent=D.gutter+'rem';radius_v.textContent=D.radius+'px';}
function readColours(){D[mode].seal=seal.value;D[mode].paper=paper.value;D[mode].ink=ink.value;}
function css(){return ':root{--seal:'+D.dark.seal+';--paper:'+D.dark.paper+';--ink:'+D.dark.ink+';--wrap:'+D.wrap+'px;--gutter:clamp(1.25rem,.8rem + 2.5vw,'+D.gutter+'rem);--radius:'+D.radius+'px;font-size:'+D.size+'%}:root[data-theme="light"]{--seal:'+D.light.seal+';--paper:'+D.light.paper+';--ink:'+D.light.ink+'}';}
function apply(){var d=pv.contentDocument;if(!d||!d.head)return;
if(mode==='light')d.documentElement.setAttribute('data-theme','light');else d.documentElement.removeAttribute('data-theme');
var s=d.getElementById('__dp');if(!s){s=d.createElement('style');s.id='__dp';d.head.appendChild(s);}s.textContent=css();}
function upd(){readShared();readColours();apply();}
['size','wrap','gutter','radius','seal','paper','ink'].forEach(function(id){document.getElementById(id).addEventListener('input',upd);});
document.querySelectorAll('#modeseg button').forEach(function(btn){btn.onclick=function(){readColours();mode=btn.getAttribute('data-mode');
document.querySelectorAll('#modeseg button').forEach(function(b){if(b===btn){b.classList.add('on');}else{b.classList.remove('on');}});
modehint.textContent='editing '+mode+' theme'+(mode==='dark'?' · switch to tune light mode':' · switch back for dark');
loadPickers();apply();};});
pv.addEventListener('load',apply);
document.getElementById('pgsel').addEventListener('change',function(){pv.src='/preview/'+this.value;});
document.getElementById('reset').onclick=function(){size.value=100;wrap.value=1140;gutter.value=3;radius.value=4;
D.dark={seal:'#2BD4E8',paper:'#1B1E24',ink:'#E9EBE7'};D.light={seal:'#077183',paper:'#F4F5F3',ink:'#16181D'};
loadPickers();upd();msg.textContent='reset to defaults (not saved yet)';};
document.getElementById('save').onclick=function(){readShared();readColours();msg.textContent='saving…';
var payload={size:D.size,wrap:D.wrap,gutter:D.gutter,radius:D.radius,seal:D.dark.seal,paper:D.dark.paper,ink:D.dark.ink,light_seal:D.light.seal,light_paper:D.light.paper,light_ink:D.light.ink};
fetch('/api/design',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
.then(function(r){return r.json();}).then(function(j){msg.textContent=j.ok?('saved \\u2713 backup '+j.backup+' \\u00b7 live now'):('error: '+j.error);})
.catch(function(e){msg.textContent='error: '+e;});};
loadPickers();readShared();
</script>
</body></html>"""


SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)

# ── GrapesJS visual (block) editor ────────────────────────────────────────
# A WordPress/Gutenberg-style drag-drop editor over each page. GrapesJS edits the
# page BODY with the real site.css loaded in its canvas, so it looks live; page
# <head>, inline <style>, and body <script>s are preserved untouched on save.
ADMIN_ASSETS = SITE / "admin-assets"
_GJS_CSS_RE = re.compile(r'<style id="gjs-css">.*?</style>', re.S)
_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)
_BODY_RE = re.compile(r"(<body[^>]*>)(.*)(</body>)", re.S | re.I)


_SHEET_RE = re.compile(
    r'<link[^>]+rel=[\'"]stylesheet[\'"][^>]*href=[\'"]([^\'"]+\.css)[\'"]', re.I)


def gjs_split(name):
    """Return (body, head_inline_css, stylesheet_hrefs) for the editor.

    The sheets are read off the page rather than assumed, because the pages
    do not all link the same one: the theme enqueues design-polish only on
    the front page and modules only on hub and modules, so build-dist.py
    bundles three different sets (site.css, site-home.css, site-tabs.css).
    Hardcoding site.css here would style the home canvas with the subpage
    cascade and move its hero by 42px.
    """
    doc = (DIST / name).read_text(encoding="utf-8")
    mb = _BODY_RE.search(doc)
    body = mb.group(2) if mb else ""
    body = _GJS_CSS_RE.sub("", body)
    body = SCRIPT_RE.sub("", body)  # scripts are re-attached on save, not edited
    head = doc[: mb.start()] if mb else doc
    inline_css = "\n".join(_STYLE_RE.findall(head))
    sheets = [h for h in _SHEET_RE.findall(head) if not h.startswith(("http:", "https:", "//"))]
    return body, inline_css, (sheets or ["assets/site.css"])


def gjs_editor_page(name):
    body, inline, sheets = gjs_split(name)
    label = PAGE_META.get(name, (name, ""))[0]
    tpl = GJS_HTML
    tpl = tpl.replace("__LABEL__", html.escape(label))
    tpl = tpl.replace("__BODY_JSON__", json.dumps(body))
    tpl = tpl.replace("__INLINE_CSS_JSON__", json.dumps(inline))
    tpl = tpl.replace("__PAGE_JSON__", json.dumps(name))
    tpl = tpl.replace("__SHEETS_JSON__", json.dumps(sheets))
    return tpl


def gjs_save(name, html_body, css):
    doc = (DIST / name).read_text(encoding="utf-8")
    mb = _BODY_RE.search(doc)
    if not mb:
        raise ValueError("no <body> in page")
    scripts = SCRIPT_RE.findall(_GJS_CSS_RE.sub("", mb.group(2)))  # preserve body scripts
    gcss = f'<style id="gjs-css">{css}</style>' if css.strip() else ""
    new_body = html_body + gcss + "".join(scripts)
    newdoc = doc[: mb.start()] + mb.group(1) + new_body + mb.group(3) + doc[mb.end():]
    b = backup(DIST / name)
    (DIST / name).write_text(newdoc, encoding="utf-8")
    return b


GJS_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>edit · entrosana</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/gjs-assets/grapes.min.css">
<style>
body{margin:0;font-family:Calibri,'Segoe UI',sans-serif}
.topbar{height:46px;display:flex;align-items:center;gap:1rem;padding:0 1rem;background:#1B1E24;color:#E9EBE7;border-bottom:1px solid #323843}
.topbar a{color:#8F95A1;text-decoration:none;font-size:.85rem}
.topbar b{font-size:.9rem}
.sp{flex:1}
.tbtn{background:#2BD4E8;color:#071316;border:0;border-radius:999px;padding:.45em 1.2em;font-weight:bold;cursor:pointer}
.tbtn.ghost{background:none;color:#E9EBE7;border:1px solid #4a505c}
#msg{font-size:.8rem;color:#8F95A1}
#gjs{height:calc(100vh - 46px)}
.gjs-block{min-height:auto;padding:.6em}
.gjs-cv-canvas,.gjs-cv-canvas__frames,.gjs-frame-wrapper{background:#101318}
</style></head><body>
<div class="topbar">
<a href="/">&larr; dashboard</a>
<b>Editing: __LABEL__</b>
<span class="sp"></span>
<span id="msg">click text to edit &middot; drag blocks from the right &middot; select an element to style it</span>
<button class="tbtn ghost" onclick="location.reload()">Discard</button>
<button class="tbtn" id="save">Save to site</button>
</div>
<div id="gjs"></div>
<script src="/gjs-assets/grapes.min.js"></script>
<script>
var BODY=__BODY_JSON__, INLINE_CSS=__INLINE_CSS_JSON__, PAGE=__PAGE_JSON__, SHEETS=__SHEETS_JSON__;
var editor=grapesjs.init({
  container:'#gjs', height:'100%', fromElement:false, storageManager:false,
  canvas:{ styles:SHEETS.map(function(h){return '/preview/'+h;}).concat(['/gjs-inline/'+PAGE]) },
  components: BODY,
  blockManager:{ blocks:[
    {id:'sec',label:'Section',category:'Blocks',content:'<section class="section"><div class="wrap"><h2 class="display h2">Heading</h2><p>Text\\u2026</p></div></section>'},
    {id:'head',label:'Heading',category:'Blocks',content:'<h2 class="display h2">Heading</h2>'},
    {id:'text',label:'Text',category:'Blocks',content:'<p>New paragraph\\u2026</p>'},
    {id:'btn',label:'Button',category:'Blocks',content:'<a class="btn" href="#">Button</a>'},
    {id:'btng',label:'Button (ghost)',category:'Blocks',content:'<a class="btn btn--ghost" href="#">Button</a>'},
    {id:'chip',label:'Chip',category:'Blocks',content:'<span class="chip">Label</span>'},
    {id:'cols',label:'2 Columns',category:'Blocks',content:'<div class="wrap split"><div><p>Left\\u2026</p></div><div><p>Right\\u2026</p></div></div>'},
    {id:'img',label:'Image',category:'Blocks',content:{type:'image'}}
  ]}
});
editor.on('load',function(){
  var d=editor.Canvas.getDocument();
  if(d&&d.head&&!d.querySelector('base')){var base=d.createElement('base');base.href='/preview/';d.head.insertBefore(base,d.head.firstChild);}
});
document.getElementById('save').onclick=function(){
  var msg=document.getElementById('msg'); msg.textContent='saving\\u2026';
  fetch('/api/gjs-save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:PAGE, html:editor.getHtml(), css:editor.getCss()})})
  .then(function(r){return r.json();}).then(function(j){msg.textContent=j.ok?('saved \\u2713 backup '+j.backup+' \\u00b7 live now'):('error: '+j.error);})
  .catch(function(e){msg.textContent='error: '+e;});
};
</script>
</body></html>"""

EDITOR_JS = """
<script id="__admin_js">
document.addEventListener('DOMContentLoaded',function(){
  document.designMode='on';
  document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a');if(a)e.preventDefault();},true);
  var bar=document.createElement('div');bar.id='__admin_bar';
  bar.style.cssText='position:fixed;bottom:18px;right:18px;z-index:99999;display:flex;gap:10px;background:#101318;border:1px solid #323843;border-radius:999px;padding:10px 14px;font-family:Calibri,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.5)';
  bar.innerHTML='<button id="__adm_save" style="background:#2BD4E8;color:#071316;border:0;border-radius:999px;padding:.5em 1.2em;font-weight:bold;cursor:pointer">Save</button>'
    +'<button id="__adm_discard" style="background:none;color:#E9EBE7;border:1px solid #4a505c;border-radius:999px;padding:.5em 1.2em;cursor:pointer">Discard</button>'
    +'<span id="__adm_msg" style="color:#8F95A1;align-self:center;font-size:13px">editing __LABEL__ · __PAGE__ (scripts off while editing)</span>';
  var badge=document.createElement('div');badge.id='__admin_badge';
  badge.style.cssText='position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:99999;background:#2BD4E8;color:#071316;font-family:Calibri,sans-serif;font-weight:bold;border-radius:999px;padding:.4em 1.2em;box-shadow:0 6px 18px rgba(0,0,0,.4)';
  badge.textContent='EDITING: __LABEL__';
  document.body.appendChild(badge);
  document.body.appendChild(bar);
  document.getElementById('__adm_discard').onclick=function(){location.reload()};
  document.getElementById('__adm_save').onclick=function(){
    var doc=document.documentElement.cloneNode(true);
    ['__admin_bar','__admin_js','__admin_base','__admin_badge'].forEach(function(id){var n=doc.querySelector('#'+id);if(n)n.remove()});
    var out='<!DOCTYPE html>'+doc.outerHTML;
    fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:'__PAGE__',html:out})})
      .then(function(r){return r.json()}).then(function(j){
        document.getElementById('__adm_msg').textContent=j.ok?('saved ✓ backup: '+j.backup):('error: '+j.error);
      }).catch(function(e){document.getElementById('__adm_msg').textContent='error: '+e});
  };
});
</script>"""

DASH_CSS = """body{margin:0;background:#1B1E24;color:#E9EBE7;font-family:Calibri,Carlito,'Segoe UI',sans-serif;padding:2rem}
a{color:#2BD4E8;text-decoration:none} a:hover{text-decoration:underline}
h1{font-size:1.6rem} .mono{font-family:Consolas,monospace;font-size:.85rem;color:#8F95A1}
table{border-collapse:collapse;margin-top:1rem} td,th{padding:.45rem .9rem;border-bottom:1px solid #323843;text-align:left}
.btn{display:inline-block;background:#2BD4E8;color:#071316;border:0;border-radius:999px;padding:.5em 1.2em;font-weight:bold;cursor:pointer;font-size:.95rem}
.btn.ghost{background:none;color:#E9EBE7;border:1px solid #4a505c}
textarea{width:100%;height:70vh;background:#101318;color:#E9EBE7;border:1px solid #323843;border-radius:8px;padding:1rem;font-family:Consolas,monospace;font-size:.85rem}
.note{color:#8F95A1;font-size:.85rem;max-width:70ch}
.ghead td{padding-top:1.4rem;color:#2BD4E8;font-size:.8rem;letter-spacing:.15em;text-transform:uppercase;border-bottom:1px solid #2BD4E8}
.desc{color:#8F95A1;font-size:.85rem;max-width:34ch}
.act{white-space:nowrap}
td b{font-size:1.05rem}
.ok{color:#57D9A3} .err{color:#FF7A7A}
.back{display:inline-block;margin-bottom:1rem;font-size:.85rem}
/* Live-Texte: viele Felder auf einer Seite. Die textarea-Regel oben ist fuer
   den Roh-Editor gedacht (genau ein Feld, 70vh); hier wird sie zurueckgenommen,
   damit das rows-Attribut wieder die Hoehe bestimmt. */
.liveform{max-width:80ch}
.liveform textarea{height:auto;field-sizing:content;padding:.5rem .7rem;
  font-size:.9rem;line-height:1.45;resize:vertical;box-sizing:border-box}
.liveform label{display:block;margin:1.1rem 0 .25rem}
.liveform h2{font-size:.95rem;margin:2.4rem 0 .2rem;color:#2BD4E8;
  border-bottom:1px solid #323843;padding-bottom:.45rem}
.liveform .savebar{position:sticky;bottom:0;background:#1B1E24;
  border-top:1px solid #323843;padding:.9rem 0;margin-top:1.5rem}
/* Telefon (2026-09-08): Tabellen werden Blöcke, Kopfzeilen verschwinden, Knöpfe
   bekommen Fingerhöhe. Die 70-vh-Regel für textarea gilt nur dem Rohtext-Editor. */
textarea[rows]{height:auto;min-height:3.2rem}
@media (max-width:760px){
  body{padding:1rem .9rem}
  h1{font-size:1.25rem;line-height:1.25} h2{font-size:1.05rem}
  table,tbody,tr,td{display:block;width:100%;box-sizing:border-box}
  thead,th,tr:has(th):not(:has(td)){display:none}
  tr{border-bottom:1px solid #323843;padding:.7rem 0}
  tr:last-child{border-bottom:0}
  td{border:0;padding:.2rem 0}
  td:empty{display:none}
  .act{white-space:normal;display:inline-block;padding:.55rem 0;min-height:44px;box-sizing:border-box}
  .desc{max-width:none}
  .btn{display:inline-block;padding:.75em 1.3em;margin:.25rem .25rem .25rem 0;min-height:44px;box-sizing:border-box}
  pre{white-space:pre-wrap;word-break:break-word;font-size:.9rem}
  .mono{overflow-wrap:anywhere}
  textarea[rows]{font-size:1rem}
}
"""


def page(title, body):
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<style>{DASH_CSS}</style></head><body>{body}</body></html>")



# ── Live-Texte (WordPress) ────────────────────────────────────────────────
# Dieser Editor pflegt die statische Seite. Die Live-Seite laeuft seit dem
# Umzug auf WordPress; ihre Texte werden hier ueber eine Schnittstelle des
# mu-plugins "entrosana Texteditor" bearbeitet. Die Pruefung, die einen
# Speichervorgang ablehnt, sobald sich eine CSS-Klasse aendern wuerde, liegt
# dort — sie gilt damit fuer diesen Weg genauso wie fuer wp-admin.

import urllib.request, urllib.error
import time


# ── Hub-Verwaltung (Konten, Bewerbungen, Anfragen) ─────────────────────────────
# Der Dienst api/ trägt die Daten; hier steht nur die Ansicht. Beiträge behalten
# ihre Konsole unter :8396, sie wird verlinkt statt kopiert.

def api_call(method, path, body=None):
    tok = API_TOKEN_FILE.read_text().strip() if API_TOKEN_FILE.exists() else ""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API_URL + path, data=data, method=method, headers={
        "X-Entrosana-Token": tok, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {"error": str(e)}
    except Exception as e:
        return 0, {"error": f"api/ nicht erreichbar: {e}"}


def _hub_wann(iso):
    return html.escape(str(iso).replace("T", " ")[:16]) if iso else "—"


def _hub_kopf(titel):
    return (f"<h1>entro<span style='color:#2BD4E8'>sana</span> admin · Hub · {titel}</h1>"
            "<p class='mono'><a href='/'>← Übersicht</a> · <a href='/hub'>Hub</a> · <a href='/hub/accounts'>Konten</a> · "
            f"<a href='/hub/applications'>Bewerbungen</a> · <a href='/hub/requests'>Anfragen</a> · <a href='/hub/checklists'>Checklisten</a> · <a href='{HUB_CONSOLE}/contributions'>Beiträge (:8396)</a></p>")


STANDING_DE = {"collector": "Sammler", "contributor": "Beitragende", "reviewer": "Team", "owner": "Eigentümer", "service": "Dienst"}
ROLE_DE = {"teacher": "Lehrperson", "student": "Lernende", "parent": "Eltern", "social-worker": "Soziale Arbeit", "developer": "Entwicklung", "researcher": "Forschung", "other": "andere"}


SEEDS_FILE = HOME / "entrosana-app" / "assets" / "seeds.js"
APP_DIR = HOME / "entrosana-app"
BACKUP_DIR = HOME / "entrosana-app-backups"


def seeds_read():
    """seeds.js ist ein Kommentarkopf plus `window.__seeds = {...};` mit striktem JSON."""
    raw = SEEDS_FILE.read_text(encoding="utf-8")
    m = re.search(r"window\.__seeds\s*=\s*(\{.*\})\s*;?\s*$", raw, re.S)
    if not m:
        raise ValueError("seeds.js: Zuweisung window.__seeds nicht gefunden")
    return raw[:m.start()], json.loads(m.group(1))


def seeds_write(head, seeds):
    """Sicherung, dann Datei neu schreiben, dann die Version in allen Seiten heben (Kante hält 4 h)."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = BACKUP_DIR / f"seeds.js.{stamp}.admin"
    bak.write_text(SEEDS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    body = json.dumps(seeds, ensure_ascii=False, indent=1)
    SEEDS_FILE.write_text(head + "window.__seeds = " + body + ";\n", encoding="utf-8")
    ver = time.strftime("%Y%m%d%H%M")
    n = 0
    for f in APP_DIR.glob("*.html"):
        s = f.read_text(encoding="utf-8")
        s2 = re.sub(r"/assets/seeds\.js(\?v=[0-9a-z]+)?\"", f"/assets/seeds.js?v={ver}\"", s)
        if s2 != s:
            f.write_text(s2, encoding="utf-8")
            n += 1
    # Bestmöglicher Commit der betroffenen Dateien (nur diese Pfade; Fehler brechen das Speichern nicht ab).
    try:
        paths = ["assets/seeds.js"] + sorted(str(f.relative_to(APP_DIR)) for f in APP_DIR.glob("*.html"))
        subprocess.run(["git", "-C", str(APP_DIR), "commit", "-q", "-m",
                        f"seeds: checkliste aus der konsole bearbeitet ({stamp})\n\nCo-Authored-By: entrosana-admin <sygnif@entrosana.com>",
                        "--"] + paths, capture_output=True, text=True, timeout=20)
    except Exception:
        pass
    return str(bak), n


def hub_checklists():
    try:
        _, seeds = seeds_read()
    except Exception as e:
        return page("Checklisten", _hub_kopf("Checklisten") + f"<p class='err'>{html.escape(str(e))}</p>")
    rows = "".join(f"<tr><td class='mono'>{html.escape(k)}</td><td><b>{html.escape(v.get('title', ''))}</b><br><span class='desc'>{html.escape(v.get('who', ''))}</span></td>"
                   f"<td class='mono'>{len(v.get('steps', []))} Schritte{(' · ' + str(len(v['prompts'])) + ' Prompts') if v.get('prompts') else ''}</td>"
                   f"<td><a class='act' href='/hub/checklists/{html.escape(k)}'>bearbeiten</a></td>"
                   f"<td><a class='act' href='https://entrosana.app/project?p={html.escape(k)}' target='_blank'>ansehen</a></td></tr>" for k, v in seeds.items())
    return page("Checklisten", _hub_kopf("Checklisten") + "<p class='note'>Die Checklisten der Projektverwaltung (assets/seeds.js). Jede Änderung wird gesichert und geht binnen 5 s live; die Seiten laden die neue Fassung mit frischer Version. "
                "Wer eine Liste schon geöffnet hat, behält seine Kopie auf dem Gerät.</p>" + f"<table><tr><th>Schlüssel</th><th>Titel</th><th>Umfang</th><th></th><th></th></tr>{rows}</table>")


def hub_checklist_edit(key):
    try:
        _, seeds = seeds_read()
    except Exception as e:
        return page("Checkliste", _hub_kopf("Checkliste") + f"<p class='err'>{html.escape(str(e))}</p>")
    s = seeds.get(key)
    if not s:
        return page("Checkliste", _hub_kopf("Checkliste") + f"<p class='err'>unbekannt: {html.escape(key)}</p>")
    def fld(label, name, value, rows=None, hint=""):
        inner = (f"<textarea name='{name}' rows='{rows}' style='width:100%;box-sizing:border-box'>{html.escape(value)}</textarea>" if rows
                 else f"<input name='{name}' value='{html.escape(value)}' style='width:100%;box-sizing:border-box'>")
        return f"<p><label><span class='mono'>{label}</span><br>{inner}</label>{('<br><span class=desc>' + hint + '</span>') if hint else ''}</p>"
    steps = s.get("steps", []) + [{}, {}]
    step_html = "".join(f"<fieldset style='border:1px solid #323843;border-radius:8px;padding:.6rem .9rem;margin:.6rem 0'><legend class='mono'>Schritt {i + 1}{'' if st else ' (leer = wird nicht gespeichert)'}</legend>"
                        + fld("Titel (t)", f"t{i}", st.get("t", "")) + fld("Zeile auf der Karte (n)", f"n{i}", st.get("n", ""), 2)
                        + fld("Details im Popup (i)", f"i{i}", st.get("i", ""), 3) + "</fieldset>" for i, st in enumerate(steps))
    form = (f"<form id='ck' data-key='{html.escape(key)}'>" + fld("Titel", "title", s.get("title", "")) + fld("Untertitel (who)", "who", s.get("who", ""))
            + fld("Prompts fürs Vorschlagsformular, eine je Zeile (leer lassen, wenn keine)", "prompts", "\n".join(s.get("prompts", [])), 6,
                  "Nur die Liste contribute/000 braucht sie: aus ihnen wird der vorbelegte Vorschlagstext.")
            + f"<h2>Schritte ({len(s.get('steps', []))})</h2><p class='note'>Reihenfolge wie hier. Ein Schritt ohne Titel fällt weg; zwei leere Blöcke stehen zum Anfügen bereit.</p>" + step_html
            + f"<div class='bar'><button class='btn' type='submit'>Speichern</button> <a class='act' href='/hub/checklists'>zurück</a> <span id='msg' class='mono'></span></div></form>"
            "<script>document.getElementById('ck').addEventListener('submit',function(e){e.preventDefault();var f=e.target,m=document.getElementById('msg');var steps=[];"
            f"for(var i=0;i<{len(steps)};i++){{var t=f['t'+i].value.trim();if(!t)continue;steps.push({{t:t,n:f['n'+i].value.trim(),i:f['i'+i].value.trim()}});}}"
            "var prompts=f.prompts.value.split('\\n').map(function(x){return x.trim()}).filter(Boolean);m.textContent='…';"
            "fetch('/hub/api/checklists/'+f.getAttribute('data-key'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:f.title.value.trim(),who:f.who.value.trim(),prompts:prompts,steps:steps})})"
            ".then(function(x){return x.json()}).then(function(j){if(j.ok){m.textContent='gespeichert · Sicherung '+j.backup+' · '+j.pages+' Seiten neu versioniert'+(j.commit?' · Commit '+j.commit:'');m.className='ok';}else{m.textContent=j.error||'Fehler';m.className='err';}})"
            ".catch(function(){m.textContent='nicht erreichbar';m.className='err';});});</script>")
    return page("Checkliste " + key, _hub_kopf("Checkliste · " + html.escape(key)) + form)


def hub_checklist_save(key, data):
    head, seeds = seeds_read()
    if key not in seeds:
        raise ValueError("unbekannte Checkliste")
    title = str(data.get("title", "")).strip()
    if len(title) < 2:
        raise ValueError("Titel fehlt")
    steps = []
    for st in data.get("steps", []):
        t = str(st.get("t", "")).strip()
        if not t:
            continue
        one = {"t": t[:200], "n": str(st.get("n", "")).strip()[:600]}
        if str(st.get("i", "")).strip():
            one["i"] = str(st.get("i", "")).strip()[:2000]
        steps.append(one)
    if not steps:
        raise ValueError("mindestens ein Schritt")
    new = dict(seeds[key])
    new["title"], new["who"], new["steps"] = title[:120], str(data.get("who", "")).strip()[:200], steps
    prompts = [str(x).strip()[:200] for x in data.get("prompts", []) if str(x).strip()]
    if prompts:
        new["prompts"] = prompts
    else:
        new.pop("prompts", None)
    seeds[key] = new
    bak, n = seeds_write(head, seeds)
    sha = subprocess.run(["git", "-C", str(APP_DIR), "log", "-1", "--format=%h", "--", "assets/seeds.js"], capture_output=True, text=True).stdout.strip()
    return {"ok": True, "backup": bak.split("/")[-1], "pages": n, "commit": sha}


def hub_dash():
    c1, actors = api_call("GET", "/api/actors")
    c2, apps = api_call("GET", "/api/applications")
    c3, reqs = api_call("GET", "/api/requests")
    c4, contribs = api_call("GET", "/api/contributions")
    if 0 in (c1, c2, c3, c4):
        return page("Hub", _hub_kopf("Übersicht") + f"<p class='err'>{html.escape(str(actors.get('error') or apps.get('error') or reqs.get('error') or contribs.get('error')))}</p>")
    offen = [c for c in contribs.get("items", []) if c.get("status") in ("received", "confirmed", "reviewing")]
    rows = (f"<tr><td><b>Konten</b><br><span class='mono'>{len([a for a in actors.get('items', []) if a.get('kind') == 'email'])} Personen</span></td><td class='desc'>Profil, Stand, Rollen, Geräte</td><td><a class='act' href='/hub/accounts'>öffnen</a></td><td></td></tr>"
            f"<tr><td><b>Bewerbungen</b><br><span class='mono'>{len(apps.get('items', []))} offen</span></td><td class='desc'>als Beitragende freigeben oder ablehnen, mit Begründung</td><td><a class='act' href='/hub/applications'>öffnen</a></td><td></td></tr>"
            f"<tr><td><b>Anfragen</b><br><span class='mono'>{len(reqs.get('items', []))} offen</span></td><td class='desc'>Module, Tracks, Werkzeuge, Dienste; gingen an info@</td><td><a class='act' href='/hub/requests'>öffnen</a></td><td></td></tr>"
            f"<tr><td><b>Beiträge</b><br><span class='mono'>{len(offen)} offen · {len(contribs.get('items', []))} gesamt</span></td><td class='desc'>Prüfung, Annahme, Veröffentlichung in der Hub-Konsole</td><td><a class='act' href='{HUB_CONSOLE}/contributions'>öffnen (:8396)</a></td><td></td></tr>"
            + "<tr><td><b>Checklisten</b><br><span class='mono'>assets/seeds.js</span></td><td class='desc'>Titel, Schritte, Kartenzeilen, Details und Formular-Prompts der Projektvorlagen</td><td><a class='act' href='/hub/checklists'>öffnen</a></td><td></td></tr>")
    return page("Hub", _hub_kopf("Übersicht") + "<p class='note'>Sammler registrieren sich frei. Beitragende und Beiträge werden hier freigegeben. Entscheide gehen der Person per Mail zu; die Kette des Dienstes hält sie fest.</p>"
                + f"<table>{rows}</table>")


def hub_accounts():
    code, j = api_call("GET", "/api/actors")
    if code != 200:
        return page("Konten", _hub_kopf("Konten") + f"<p class='err'>{html.escape(str(j.get('error', code)))}</p>")
    rows = ""
    for a in j.get("items", []):
        pr = a.get("profile") or {}
        profil = " · ".join(x for x in [ROLE_DE.get(pr.get("role"), pr.get("role") or ""), pr.get("org") or "", ", ".join(pr.get("langs") or [])] if x)
        about = f"<br><span class='desc'>{html.escape(pr.get('about'))}</span>" if pr.get("about") else ""
        web = f"<br><a class='act' href='{html.escape(pr.get('website'))}' target='_blank' rel='noopener'>{html.escape(pr.get('website'))}</a>" if pr.get("website") else ""
        rollen = ", ".join(a.get("roles") or []) or "—"
        rows += (f"<tr><td class='mono'>#{a['id']}</td><td><b>{html.escape(a.get('name') or '—')}</b><br><span class='mono'>{html.escape(a.get('email') or a.get('kind'))}</span>{about}{web}</td>"
                 f"<td>{html.escape(STANDING_DE.get(a.get('standing'), a.get('standing')))}<br><span class='mono'>{html.escape(rollen)}</span></td>"
                 f"<td class='desc'>{html.escape(profil) or '—'}</td>"
                 f"<td class='mono'>{a.get('contributions')} Beiträge<br>{a.get('open_applications')} Bewerbungen<br>{a.get('devices')} Geräte</td>"
                 f"<td class='mono'>{_hub_wann(a.get('created'))}</td></tr>")
    hinweis = ("<p class='note'>Rollen vergibt der Eigentümer auf dem Server: <span class='mono'>node ~/entrosana-app/api/admin.mjs grant &lt;email&gt; reviewer</span>. "
               "Beitragende entstehen über <a href='/hub/applications'>Bewerbungen</a>.</p>")
    return page("Konten", _hub_kopf("Konten") + hinweis + f"<table><tr><th></th><th>Person</th><th>Stand · Rollen</th><th>Profil</th><th>Zahlen</th><th>seit</th></tr>{rows}</table>")


def hub_applications():
    code, j = api_call("GET", "/api/applications?all=1")
    if code != 200:
        return page("Bewerbungen", _hub_kopf("Bewerbungen") + f"<p class='err'>{html.escape(str(j.get('error', code)))}</p>")
    items = j.get("items", [])
    offen = [a for a in items if not a.get("decided")]
    alt = [a for a in items if a.get("decided")]
    rows = ""
    for a in offen:
        aid = a["id"]
        rows += (f"<tr><td class='mono'>#{aid}</td><td><b>{html.escape(a.get('actor_name') or '—')}</b><br><span class='mono'>{html.escape(a.get('actor_email') or '')}</span></td>"
                 f"<td class='mono'>{_hub_wann(a.get('created'))}</td><td><pre style='white-space:pre-wrap;margin:0'>{html.escape(a.get('text', ''))}</pre></td></tr>"
                 f"<tr><td></td><td colspan='3'><textarea id='r{aid}' rows='2' style='width:100%' placeholder='Begründung, mindestens drei Zeichen; sie geht per Mail an die Person'></textarea><br>"
                 f"<button class='btn' data-app='{aid}' data-out='approved'>freigeben</button> <button class='btn' data-app='{aid}' data-out='declined'>ablehnen</button> <span id='m{aid}' class='mono'></span></td></tr>")
    t_offen = f"<h2>Offen ({len(offen)})</h2><table><tr><th></th><th>Person</th><th>eingegangen</th><th>Bewerbung</th></tr>{rows}</table>" if offen else "<h2>Offen</h2><p class='mono'>keine</p>"
    rows2 = "".join(f"<tr><td class='mono'>#{a['id']}</td><td>{html.escape(a.get('actor_name') or '—')}<br><span class='mono'>{html.escape(a.get('actor_email') or '')}</span></td>"
                    f"<td class='{'ok' if a.get('outcome') == 'approved' else 'err'}'>{'freigegeben' if a.get('outcome') == 'approved' else 'abgelehnt'}</td>"
                    f"<td class='mono'>{_hub_wann(a.get('decided'))} · Akteur {a.get('decided_by')}</td><td>{html.escape(a.get('reason') or '')}</td></tr>" for a in alt)
    t_alt = f"<h2>Entschieden ({len(alt)})</h2><table><tr><th></th><th>Person</th><th>Ausgang</th><th>wann</th><th>Begründung</th></tr>{rows2}</table>" if alt else ""
    script = ("<script>document.querySelectorAll('button[data-app]').forEach(function(b){b.addEventListener('click',function(){"
              "var id=b.getAttribute('data-app'),out=b.getAttribute('data-out'),r=document.getElementById('r'+id).value.trim(),m=document.getElementById('m'+id);"
              "if(r.length<3){m.textContent='Begründung fehlt.';m.className='err';return;}m.textContent='…';m.className='mono';"
              "fetch('/hub/api/applications/'+id+'/decide',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({outcome:out,reason:r})})"
              ".then(function(x){return x.json()}).then(function(j){if(j.ok){location.reload();}else{m.textContent=j.error||'Fehler';m.className='err';}})"
              ".catch(function(){m.textContent='Dienst nicht erreichbar';m.className='err';});});});</script>")
    return page("Bewerbungen", _hub_kopf("Bewerbungen") + t_offen + t_alt + script)


def hub_requests(alle=False):
    code, j = api_call("GET", "/api/requests" + ("?all=1" if alle else ""))
    if code != 200:
        return page("Anfragen", _hub_kopf("Anfragen") + f"<p class='err'>{html.escape(str(j.get('error', code)))}</p>")
    items = j.get("items", [])
    rows = ""
    for r in items:
        rid = r["id"]
        knopf = (f"<button class='btn' data-req='{rid}' data-h='0'>wieder öffnen</button>" if r.get("handled")
                 else f"<button class='btn' data-req='{rid}' data-h='1'>erledigt</button>")
        rows += (f"<tr><td class='mono'>#{rid}</td><td><b>{html.escape(r.get('name') or '')}</b><br><span class='mono'>{html.escape(r.get('email') or '')}</span>"
                 f"{('<br>' + html.escape(r.get('org'))) if r.get('org') else ''}</td><td class='mono'>{html.escape(r.get('kind') or '')}</td>"
                 f"<td><pre style='white-space:pre-wrap;margin:0'>{html.escape(r.get('text') or '')}</pre></td>"
                 f"<td class='mono'>{_hub_wann(r.get('created'))}<br>{'Mail an info@ ' + _hub_wann(r.get('mailed')) if r.get('mailed') else '<span class=\'err\'>Mail nicht belegt</span>'}"
                 f"{('<br>erledigt ' + _hub_wann(r.get('handled'))) if r.get('handled') else ''}</td><td>{knopf} <span id='m{rid}' class='mono'></span></td></tr>")
    umschalter = ("<p class='mono'>" + ("<a href='/hub/requests'>nur offene</a>" if alle else "<a href='/hub/requests?all=1'>alle, auch erledigte</a>") + "</p>")
    tab = f"<table><tr><th></th><th>Person</th><th>Art</th><th>Anfrage</th><th>wann</th><th></th></tr>{rows}</table>" if items else "<p class='mono'>keine</p>"
    script = ("<script>document.querySelectorAll('button[data-req]').forEach(function(b){b.addEventListener('click',function(){"
              "var id=b.getAttribute('data-req'),h=b.getAttribute('data-h')==='1',m=document.getElementById('m'+id);m.textContent='…';"
              "fetch('/hub/api/requests/'+id+'/handled',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({handled:h})})"
              ".then(function(x){return x.json()}).then(function(j){if(j.ok){location.reload();}else{m.textContent=j.error||'Fehler';m.className='err';}})"
              ".catch(function(){m.textContent='Dienst nicht erreichbar';m.className='err';});});});</script>")
    return page("Anfragen", _hub_kopf("Anfragen") + "<p class='note'>Anfragen gingen als Mail an info@entrosana.com; hier steht der Eingang 180 Tage. «erledigt» ist eine Marke, keine Löschung.</p>" + umschalter + tab + script)


WP_BASE = "http://127.0.0.1:8090/wp-json/entrosana/v1"
WP_TOKEN_FILE = HOME / ".config" / "entrosana-textapi.token"


def wp_token():
    try:
        return WP_TOKEN_FILE.read_text().strip()
    except OSError:
        return ""


def wp_call(path, payload=None, timeout=25):
    """Ruft die Schnittstelle des Plugins auf. Gibt (ok, daten_oder_fehlertext)."""
    tok = wp_token()
    if not tok:
        return False, f"Token fehlt: {WP_TOKEN_FILE}"
    req = urllib.request.Request(
        WP_BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method="POST" if payload is not None else "GET",
        headers={"X-Entrosana-Token": tok, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return False, str(e)


def live_index_page(msg=""):
    ok, data = wp_call("/texts")
    if not ok:
        return page("entrosana · Live-Texte",
                    "<div class='wrap'><a class='back' href='/'>&larr; dashboard</a>"
                    f"<h1>Live-Texte</h1><p class='err'>Nicht erreichbar: {html.escape(str(data))}</p></div>")
    rows = "".join(
        f"<tr><td><b>{html.escape(p['title'])}</b></td>"
        f"<td><a class='act' href='/live/{p['id']}'>Texte bearbeiten</a></td>"
        f"<td><a class='act' href='{html.escape(p['url'])}' target='_blank'>ansehen</a></td></tr>"
        for p in data)
    return page("entrosana · Live-Texte",
                "<div class='wrap'><a class='back' href='/'>&larr; dashboard</a>"
                "<h1>Live-Texte</h1>"
                "<p>Die Seiten unter entrosana.com. Hier aendert sich ausschliesslich Text — "
                "Markup, Klassen und Layout bleiben unberuehrt. Ein Speichervorgang, der die "
                "Klassenliste veraendern wuerde, wird abgelehnt.</p>"
                + (f"<p class='ok'>{html.escape(msg)}</p>" if msg else "")
                + f"<table>{rows}</table></div>")


def live_edit_page(pid, msg="", err=""):
    ok, d = wp_call(f"/texts/{pid}")
    if not ok:
        return page("entrosana · Live-Texte",
                    "<div class='wrap'><a class='back' href='/live'>&larr; zurueck</a>"
                    f"<h1>Seite {pid}</h1><p class='err'>{html.escape(str(d))}</p></div>")
    parts = []
    n = 0
    for sec in d["sections"]:
        head = f" &middot; <span style='font-weight:400'>{html.escape(sec['heading'][:60])}</span>" if sec["heading"] else ""
        parts.append(f"<h2>Abschnitt {sec['i'] + 1}{head}</h2>")
        for it in sec["items"]:
            n += 1
            cls = f" <span class='mono' style='opacity:.6'>{html.escape(it['class'])}</span>" if it["class"] else ""
            rows = max(2, min(9, len(it["html"]) // 90 + 1))
            parts.append(
                f"<label><span class='mono'>{html.escape(it['tag'])}</span>{cls}</label>"
                f"<textarea name='t[{sec['i']}][{it['i']}]' rows='{rows}'>{html.escape(it['html'])}</textarea>")
    body = ("<div class='wrap'><a class='back' href='/live'>&larr; zurueck</a>"
            f"<h1>{html.escape(d['title'])}</h1>"
            f"<p class='mono' style='opacity:.7'>Quelle: {html.escape(d['source'])} &middot; "
            f"<a href='{html.escape(d['url'])}' target='_blank'>Seite ansehen</a></p>"
            + (f"<p class='ok'>{html.escape(msg)}</p>" if msg else "")
            + (f"<p class='err'>{html.escape(err)}</p>" if err else "")
            + f"<form class='liveform' method='post' action='/live/{pid}'>" + "".join(parts)
            + f"<p class='savebar'><button class='btn'>{n} Textstellen speichern</button></p></form></div>")
    return page(f"entrosana · {d['title']}", body)

# ── inline-style sanitiser ────────────────────────────────────────────────
# designMode bakes presentational inline styles (background-color, color,
# font-family) into edited text; those then fight the theme stylesheet — e.g. a
# captured dark background-color shows as a black highlight box in light mode.
# Strip exactly those declarations from every save; keep anything else.
_STYLE_ATTR_RE = re.compile(r'\s*style="([^"]*)"')
_CRUFT_PROPS = ("background-color", "background", "color", "font-family")


def sanitize_inline_styles(doc: str) -> str:
    def repl(m):
        decls = [d.strip() for d in m.group(1).split(";") if d.strip()]
        kept = [d for d in decls if d.split(":", 1)[0].strip().lower() not in _CRUFT_PROPS]
        return (' style="' + ";".join(kept) + '"') if kept else ""
    return _STYLE_ATTR_RE.sub(repl, doc)


# ── footer editor ─────────────────────────────────────────────────────────
# Plain-text-in, clean-markup-out footer editor for the landing page. Because
# only text/urls are stored and the markup is regenerated, no inline styles can
# ever be introduced — so the highlight-box problem cannot recur here.
_FOOTER_RE = re.compile(r'<footer class="foot">.*?</footer>', re.S)
_FCOL_RE = re.compile(r'<div><span class="foot__h mono">(.*?)</span>(.*?)</div>', re.S)
_FITEM_RE = re.compile(r'<a href="([^"]*)"[^>]*>(.*?)</a>|<span class="muted">(.*?)</span>', re.S)


def _striptags(s: str) -> str:
    # fields are plain text: drop any wrapper tags (e.g. editor-injected spans)
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _footer_items_to_text(inner: str) -> str:
    lines = []
    for m in _FITEM_RE.finditer(inner):
        if m.group(1) is not None:
            lines.append(f"{_striptags(m.group(2))} | {html.unescape(m.group(1)).strip()}")
        elif m.group(3) is not None:
            lines.append(_striptags(m.group(3)))
    return "\n".join(lines)


def _footer_text_to_items(text: str) -> str:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            label, href = (s.strip() for s in line.split("|", 1))
            rel = ' rel="noopener"' if href.lower().startswith("http") else ""
            out.append(f'<a href="{html.escape(href)}"{rel}>{html.escape(label)}</a>')
        else:
            out.append(f'<span class="muted">{html.escape(line)}</span>')
    return "".join(out)


def footer_read() -> dict:
    doc = (DIST / "index.html").read_text(encoding="utf-8")
    m = _FOOTER_RE.search(doc)
    blk = m.group(0) if m else ""

    def one(pat, d=""):
        mm = re.search(pat, blk, re.S)
        return _striptags(mm.group(1)) if mm else d

    v = {"tagline": one(r'foot__brand.*?<p class="muted">(.*?)</p>'),
         "copyright": one(r'foot__base.*?<span class="mono muted">(.*?)</span>'),
         "cols": []}
    for mm in _FCOL_RE.finditer(blk):
        v["cols"].append({"head": _striptags(mm.group(1)),
                          "items": _footer_items_to_text(mm.group(2))})
    while len(v["cols"]) < 3:
        v["cols"].append({"head": "", "items": ""})
    return v


def footer_render(v: dict) -> str:
    cols = ""
    for c in v["cols"][:3]:
        cols += (f'<div><span class="foot__h mono">{html.escape(c["head"])}</span>\n'
                 f'{_footer_text_to_items(c["items"])}</div>\n')
    return (
        '<footer class="foot"><div class="wrap foot__inner">\n'
        '<div class="foot__brand"><span class="foot__word mono">entro<b class="brand__accent">sana</b></span>\n'
        f'<p class="muted">{html.escape(v["tagline"])}</p></div>\n'
        '<nav class="foot__cols" aria-label="Footer">\n'
        f'{cols}</nav></div>\n'
        '<div class="wrap foot__base">\n'
        f'<span class="mono muted">{html.escape(v["copyright"])}</span>\n'
        '</div>\n</footer>'
    )


def footer_write(v: dict) -> str:
    f = DIST / "index.html"
    doc = f.read_text(encoding="utf-8")
    if not _FOOTER_RE.search(doc):
        raise ValueError("footer block not found")
    doc = _FOOTER_RE.sub(lambda m: footer_render(v), doc, count=1)
    doc = restamp(doc)
    b = backup(f)
    f.write_text(doc, encoding="utf-8")
    return b


def footer_page() -> str:
    v = footer_read()
    inp = ("width:100%;padding:.5em;border-radius:8px;border:1px solid #323843;"
           "background:#101318;color:#E9EBE7")

    def col_field(i, c):
        return (f"<h3 class='mono' style='color:#2BD4E8;margin-top:1.6rem'>Column {i+1}</h3>"
                f"<label style='display:block;margin:.6rem 0'>Heading<br>"
                f"<input id='c{i}h' value=\"{html.escape(c['head'], quote=True)}\" style='{inp}'></label>"
                "<label style='display:block;margin:.6rem 0'>Links — one per line as "
                "<span class='mono'>Label | /url</span> (leave off <span class='mono'>| /url</span> for plain text)<br>"
                f"<textarea id='c{i}' style='height:8rem'>{html.escape(c['items'])}</textarea></label>")

    cols = "".join(col_field(i, c) for i, c in enumerate(v["cols"][:3]))
    body = (
        "<h1>Footer</h1>"
        "<p class='note'>Edits the landing-page footer. Plain text only, the markup is regenerated on save — "
        "so no styling is ever stored and the black-highlight problem cannot happen here. "
        "Every save makes a backup and goes live immediately.</p>"
        "<div style='max-width:64ch'>"
        f"<label style='display:block;margin:.6rem 0'>Tagline<br><textarea id='tag' style='height:4rem'>{html.escape(v['tagline'])}</textarea></label>"
        f"{cols}"
        f"<label style='display:block;margin:1.4rem 0 .6rem'>Copyright line<br><input id='cop' value=\"{html.escape(v['copyright'], quote=True)}\" style='{inp}'></label>"
        "<p style='margin-top:1.4rem'><button class='btn' id='save'>Save footer</button> "
        "<a class='btn ghost' href='/'>Back</a> <span id='msg' class='mono' style='margin-left:1rem'></span></p>"
        "</div>"
        "<script>document.getElementById('save').onclick=function(){"
        "var cols=[];for(var i=0;i<3;i++){cols.push({head:document.getElementById('c'+i+'h').value,items:document.getElementById('c'+i).value});}"
        "var v={tagline:document.getElementById('tag').value,copyright:document.getElementById('cop').value,cols:cols};"
        "var m=document.getElementById('msg');m.textContent='saving\\u2026';"
        "fetch('/api/footer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(v)})"
        ".then(function(r){return r.json()}).then(function(j){m.textContent=j.ok?('saved \\u2713 backup '+j.backup+' \\u00b7 live now'):('error: '+j.error);})"
        ".catch(function(e){m.textContent='error: '+e});};</script>"
    )
    return page("entrosana footer", body)


class H(BaseHTTPRequestHandler):
    server_version = "entrosana-admin"

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Robots-Tag", "noindex")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _authed(self):
        if TAILNET_OPEN and self._src_ok():
            return True
        m = SimpleCookie(self.headers.get("Cookie", "")).get("eak")
        return bool(TOKEN) and m is not None and hmac.compare_digest(m.value, TOKEN)

    def _src_ok(self):
        # tailnet-only enforcement (the bind is 0.0.0.0): allow loopback + the
        # tailscale CGNAT range only. TCP source IPs can't be spoofed into a
        # completed handshake, so this closes off-tailnet/LAN reachability.
        ip = self.client_address[0]
        if ip in ("127.0.0.1", "::1"):
            return True
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10")
        except ValueError:
            return False

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        if not self._src_ok():
            self._send(403, "forbidden", "text/plain")
            return
        u = urlparse(self.path)
        q = parse_qs(u.query)
        # login
        if u.path == "/login":
            key = q.get("key", [""])[0]
            if TOKEN and hmac.compare_digest(key, TOKEN):
                self._send(302, "", extra={"Set-Cookie": f"eak={TOKEN}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000",
                                           "Location": "/"})
            else:
                self._send(200, page("entrosana admin · login",
                    "<h1>entro<span style='color:#2BD4E8'>sana</span> admin</h1>"
                    "<form action='/login'><input name='key' type='password' placeholder='access key' "
                    "style='padding:.5em .8em;border-radius:8px;border:1px solid #323843;background:#101318;color:#E9EBE7'>"
                    " <button class='btn'>Enter</button></form>"))
            return
        if not self._authed():
            self._send(302, "", extra={"Location": "/login"})
            return
        # dashboard
        if u.path == "/hub":
            self._send(200, hub_dash())
            return
        if u.path == "/hub/checklists":
            self._send(200, hub_checklists())
            return
        mck = re.match(r"^/hub/checklists/([a-z]+/\d{3})$", u.path)
        if mck:
            self._send(200, hub_checklist_edit(mck.group(1)))
            return
        if u.path == "/hub/accounts":
            self._send(200, hub_accounts())
            return
        if u.path == "/hub/applications":
            self._send(200, hub_applications())
            return
        if u.path == "/hub/requests":
            self._send(200, hub_requests(q.get("all", [""])[0] == "1"))
            return
        if u.path == "/live":
            self._send(200, live_index_page())
            return
        ml = re.match(r"^/live/(\d+)$", u.path)
        if ml:
            self._send(200, live_edit_page(int(ml.group(1))))
            return
        if u.path == "/":
            # Was wirklich unter entrosana.com steht. Faellt die Bruecke aus,
            # sagt die Seite das und bleibt bedienbar — der Altbestand unten
            # haengt nicht daran.
            ok, live = wp_call("/texts")
            if ok:
                live_rows = "".join(
                    f"<tr><td><b>{html.escape(p['title'])}</b><br>"
                    f"<span class='mono'>{html.escape(p['url'].replace('https://entrosana.com', '') or '/')}</span></td>"
                    f"<td class='desc'>Text bearbeiten, Markup und Klassen bleiben unberuehrt</td>"
                    f"<td><a class='act' href='/live/{p['id']}'>Texte bearbeiten</a></td>"
                    f"<td><a class='act' href='{html.escape(p['url'])}' target='_blank'>ansehen</a></td></tr>"
                    for p in live)
                live_note = f"{len(live)} Seiten"
            else:
                live_rows = ("<tr><td colspan='4' class='err'>Bruecke nicht erreichbar: "
                             f"{html.escape(str(live))}</td></tr>")
                live_note = "nicht erreichbar"

            hub_row = ("<tr><td><b>Hub</b><br><span class='mono'>Konten &middot; Bewerbungen &middot; Anfragen</span></td>"
                       "<td class='desc'>Sammler und Beitragende, Freigaben, Anfragen an info@; Beitr&auml;ge in der Hub-Konsole :8396</td>"
                       "<td><a class='act' href='/hub'>oeffnen</a></td><td></td></tr>"
                       "<tr><td><b>Checklisten</b><br><span class='mono'>Projektverwaltung &middot; assets/seeds.js</span></td>"
                       "<td class='desc'>Vorlagen der Projektverwaltung auf entrosana.app: Titel, Schritte, Kartenzeilen, Details, Formular-Prompts; "
                       "mit Sicherung, Versionshebung und Commit</td>"
                       "<td><a class='act' href='/hub/checklists'>oeffnen</a></td><td></td></tr>")
            gestaltung = (
                "<tr><td><b>Design controls</b><br><span class='mono'>Schriftgroesse &middot; Farbe &middot; Raster</span></td>"
                "<td class='desc'>schreibt den verwalteten Block in <span class='mono'>theme/entrosana/assets/site.css</span> &mdash; "
                "sofort auf entrosana.com sichtbar, mit Sicherung</td>"
                "<td><a class='act' href='/design'>oeffnen</a></td><td></td></tr>")

            act = subprocess.run(["systemctl", "--user", "is-active", "entrosana-site"],
                                 capture_output=True, text=True).stdout.strip()

            def row(fname, label, desc, stub_to=None):
                acts = ("<span class='mono' style='color:#4a505c'>redirect only</span>" if stub_to
                        else f"<a class='act' href='/gjs/{fname}'>visual editor</a> &middot; "
                             f"<a class='act' href='/edit/{fname}'>text</a>")
                desc_html = f"redirects old URL to {stub_to}" if stub_to else desc
                return (f"<tr><td><b>{label}</b><br><span class='mono'>{fname}</span></td>"
                        f"<td class='desc'>{desc_html}</td>"
                        f"<td>{acts}</td>"
                        f"<td><a class='act' href='/raw?f=dist/{fname}'>raw</a></td>"
                        f"<td><a class='act' href='/preview/{fname}' target='_blank'>preview</a></td></tr>")

            rows = ""
            known = set()
            for gtitle, names in GROUPS:
                rows += f"<tr class='ghead'><td colspan='5'>{gtitle}</td></tr>"
                for n in names:
                    if (DIST / n).exists():
                        known.add(n)
                        label, desc = PAGE_META[n]
                        rows += row(n, label, desc)
            stubs = [f for f in sorted(DIST.glob("*.html")) if f.name not in known and is_stub(f)]
            others = [f for f in sorted(DIST.glob("*.html")) if f.name not in known and not is_stub(f)]
            if stubs:
                rows += "<tr class='ghead'><td colspan='5'>Redirects (alte v1-URLs)</td></tr>"
                for f in stubs:
                    rows += row(f.name, f.name[:-5], "", stub_to=stub_target(f))
            if others:
                rows += "<tr class='ghead'><td colspan='5'>Weitere Seiten</td></tr>"
                for f in others:
                    rows += row(f.name, f.name[:-5], "")
            rows += ("<tr class='ghead'><td colspan='5'>Server und Fusszeile</td></tr>"
                     "<tr><td><b>Server</b><br><span class='mono'>server.mjs</span></td>"
                     "<td class='desc'>Node-Server der statischen Fassung; nach Aenderungen neu starten</td><td></td>"
                     "<td><a class='act' href='/raw?f=server.mjs'>raw</a></td><td></td></tr>"
                     + "".join(
                         "<tr><td><b>Stylesheet</b><br>"
                         f"<span class='mono'>dist/assets/{n}</span></td>"
                         "<td class='desc'>Stylesheet der statischen Fassung &mdash; "
                         "von <span class='mono'>build-dist.py</span> aus dem Theme "
                         "gebaut, in der Reihenfolge der jeweiligen Seite</td><td></td>"
                         f"<td><a class='act' href='/raw?f=dist/assets/{n}'>raw</a></td>"
                         "<td></td></tr>"
                         for n in dist_bundles())
                     +
                     "<tr><td><b>Fusszeile</b><br><span class='mono'>tagline &middot; Spalten &middot; Copyright</span></td>"
                     "<td class='desc'>bearbeitet die Fusszeile der statischen Startseite</td>"
                     "<td><a class='act' href='/footer'>oeffnen</a></td><td></td><td></td></tr>")

            body = (
                "<h1>entro<span style='color:#2BD4E8'>sana</span> admin</h1>"
                "<h2 style='margin-top:1.6rem'>entrosana.com &mdash; die Live-Seite</h2>"
                f"<p class='mono'>WordPress hinter dem Tunnel &middot; {live_note}</p>"
                f"<table>{live_rows}</table>"
                "<h2 style='margin-top:2.4rem'>Gestaltung</h2>"
                f"<table>{hub_row}{gestaltung}</table>"
                "<h2 style='margin-top:2.4rem'>Altbestand: statische Fassung</h2>"
                f"<p class='mono'>Dienst entrosana-site: {act} &middot; "
                "<button class='btn ghost' onclick=\"fetch('/api/restart',{method:'POST'}).then(r=>r.json()).then(j=>alert(JSON.stringify(j)))\">Dienst neu starten</button> "
                "<button class='btn ghost' onclick=\"fetch('/api/backup-all',{method:'POST'}).then(r=>r.json()).then(j=>alert(JSON.stringify(j)))\">alles sichern</button></p>"
                "<p class='note'>Diese Dateien liegen in <span class='mono'>~/entrosana-site/dist</span> und werden vom Node-Server "
                "auf Port 4321 ausgeliefert, nicht von entrosana.com. Was hier geaendert wird, erscheint dort &mdash; "
                "auf der Live-Seite aendert es nichts. Jede Speicherung legt eine Sicherung an "
                "(<span class='mono'>dist-backups/</span>, die letzten 20).</p>"
                f"<table>{rows}</table>")
            self._send(200, page("entrosana admin", body))
            return
        # visual editor
        m = re.match(r"^/edit/([a-z0-9-]+\.html)$", u.path)
        if m:
            f = DIST / m.group(1)
            if not f.exists():
                self._send(404, "not found", "text/plain")
                return
            if is_stub(f):
                self._send(200, page("redirect stub", f"<h1>{m.group(1)} is a redirect stub</h1>"
                    f"<p class='note'>It forwards an old v1 URL to {stub_target(f)} and has no editable content. Use the raw editor if you must change its target.</p>"
                    f"<p><a class='btn ghost' href='/'>Back</a> <a class='btn' href='/raw?f=dist/{m.group(1)}'>Open raw</a></p>"))
                return
            doc = f.read_text(encoding="utf-8")
            doc = SCRIPT_RE.sub("", doc)  # freeze the DOM while editing
            doc = doc.replace("<head>", "<head><base id=\"__admin_base\" href=\"/preview/\">", 1)
            label = PAGE_META.get(m.group(1), (m.group(1), ""))[0]
            doc = doc.replace("</body>", EDITOR_JS.replace("__PAGE__", m.group(1)).replace("__LABEL__", label) + "</body>")
            self._send(200, doc)
            return
        # raw editor
        if u.path == "/raw":
            rel = q.get("f", [""])[0]
            p = resolve_raw(rel)
            if not p:
                self._send(404, "not in allowlist", "text/plain")
                return
            content = html.escape(p.read_text(encoding="utf-8"))
            body = (f"<h1 class='mono'>{rel}</h1>"
                    f"<textarea id='t'>{content}</textarea><p>"
                    f"<button class='btn' onclick=\"fetch('/api/raw',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{file:'{rel}',content:document.getElementById('t').value}})}}).then(r=>r.json()).then(j=>alert(JSON.stringify(j)))\">Save</button> "
                    "<a class='btn ghost' href='/'>Back</a></p>"
                    "<p class='note'>server.mjs changes need a site restart to take effect (button on the dashboard).</p>")
            self._send(200, page(f"raw · {rel}", body))
            return
        # static preview of dist
        if u.path.startswith("/preview/"):
            rel = u.path[len("/preview/"):] or "index.html"
            p = (DIST / rel).resolve()
            if p.is_relative_to(DIST) and p.is_file():
                self._send(200, p.read_bytes(), CTYPES.get(p.suffix, "application/octet-stream"))
            else:
                self._send(404, "not found", "text/plain")
            return
        # design controls
        if u.path == "/design":
            self._send(200, design_page())
            return
        # footer editor
        if u.path == "/footer":
            self._send(200, footer_page())
            return
        # GrapesJS library assets
        if u.path.startswith("/gjs-assets/"):
            p = (ADMIN_ASSETS / u.path[len("/gjs-assets/"):]).resolve()
            if p.is_relative_to(ADMIN_ASSETS) and p.is_file():
                self._send(200, p.read_bytes(), CTYPES.get(p.suffix, "application/octet-stream"))
            else:
                self._send(404, "not found", "text/plain")
            return
        # GrapesJS visual editor
        mg = re.match(r"^/gjs/([a-z0-9-]+\.html)$", u.path)
        if mg:
            f = DIST / mg.group(1)
            if not f.exists() or is_stub(f):
                self._send(404, "not editable", "text/plain")
                return
            self._send(200, gjs_editor_page(mg.group(1)))
            return
        # page's inline <head> CSS, served as a stylesheet for the canvas
        mi = re.match(r"^/gjs-inline/([a-z0-9-]+\.html)$", u.path)
        if mi:
            f = DIST / mi.group(1)
            if f.exists():
                doc = f.read_text(encoding="utf-8")
                mb = _BODY_RE.search(doc)
                head = doc[: mb.start()] if mb else doc
                css = "\n".join(_STYLE_RE.findall(head))
                # editor-canvas chrome: GrapesJS resets the body to white (hides the
                # light-on-dark text) and does not run entrance animations (which start
                # elements at opacity:0), so force a dark bg + all content visible.
                css += (
                    "\n/* gjs canvas chrome */\n"
                    "html,body{background:#1B1E24 !important}\n"
                    "*{opacity:1 !important;animation:none !important;transition:none !important}\n"
                    "[style*='opacity:0'],[style*='opacity: 0']{opacity:1 !important}\n"
                )
                self._send(200, css, "text/css; charset=utf-8")
            else:
                self._send(404, "not found", "text/plain")
            return
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        if not self._src_ok():
            self._json({"ok": False, "error": "forbidden"}, 403)
            return
        if not self._authed():
            self._json({"ok": False, "error": "auth"}, 403)
            return
        u = urlparse(self.path)
        ln = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(ln) if ln else b""
        mlp = re.match(r"^/live/(\d+)$", u.path)
        if mlp:
            pid = int(mlp.group(1))
            fields = parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
            t = {}
            for k, v in fields.items():
                m = re.match(r"^t\[(\d+)\]\[(\d+)\]$", k)
                if m:
                    t.setdefault(m.group(1), {})[m.group(2)] = v[0]
            ok, res = wp_call(f"/texts/{pid}", {"t": t})
            if ok and res.get("ok"):
                self._send(200, live_edit_page(pid, msg=res.get("message", "gespeichert")))
            else:
                detail = res.get("message") if isinstance(res, dict) else str(res)
                self._send(200, live_edit_page(pid, err=detail or "Speichern fehlgeschlagen"))
            return
        mcs = re.match(r"^/hub/api/checklists/([a-z]+/\d{3})$", u.path)
        if mcs:
            try:
                self._json(hub_checklist_save(mcs.group(1), json.loads(raw or b"{}")))
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return
        mh = re.match(r"^/hub/api/(applications|requests)/(\d{1,12})/(decide|handled)$", u.path)
        if mh:
            try:
                body = json.loads(raw or b"{}")
                if mh.group(1) == "applications" and mh.group(3) == "decide":
                    reason = str(body.get("reason", "")).strip()
                    if len(reason) < 3:
                        raise ValueError("Begründung fehlt")
                    code, res = api_call("PATCH", f"/api/applications/{mh.group(2)}", {"outcome": body.get("outcome", ""), "reason": reason})
                elif mh.group(1) == "requests" and mh.group(3) == "handled":
                    code, res = api_call("PATCH", f"/api/requests/{mh.group(2)}", {"handled": bool(body.get("handled"))})
                else:
                    raise ValueError("unbekannter Pfad")
                if code != 200:
                    raise ValueError(str(res.get("error", code)))
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return
        if u.path == "/api/save":
            try:
                data = json.loads(raw)
                name = data["name"]
                if not re.match(r"^[a-z0-9-]+\.html$", name):
                    raise ValueError("bad name")
                f = DIST / name
                original = f.read_text(encoding="utf-8")
                scripts = SCRIPT_RE.findall(original)
                doc = data["html"]
                doc = SCRIPT_RE.sub("", doc)  # belt and braces
                doc = sanitize_inline_styles(doc)  # strip designMode's inline colour/bg/font cruft
                doc = doc.replace("</body>", "".join(scripts) + "</body>")
                doc = restamp(doc)
                b = backup(f)
                f.write_text(doc, encoding="utf-8")
                self._json({"ok": True, "backup": b})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return
        if u.path == "/api/raw":
            try:
                data = json.loads(raw)
                p = resolve_raw(data["file"])
                if not p:
                    raise ValueError("not in allowlist")
                b = backup(p)
                p.write_text(data["content"], encoding="utf-8")
                self._json({"ok": True, "backup": b})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return
        if u.path == "/api/gjs-save":
            try:
                data = json.loads(raw)
                name = data["name"]
                if not re.match(r"^[a-z0-9-]+\.html$", name):
                    raise ValueError("bad name")
                b = gjs_save(name, data["html"], data.get("css", ""))
                self._json({"ok": True, "backup": b})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return
        if u.path == "/api/design":
            try:
                v = _validate_design(json.loads(raw))
                b = write_design(v)
                self._json({"ok": True, "backup": b})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return
        if u.path == "/api/footer":
            try:
                data = json.loads(raw)
                cols = [{"head": str(c.get("head", "")), "items": str(c.get("items", ""))}
                        for c in (data.get("cols") or [])][:3]
                while len(cols) < 3:
                    cols.append({"head": "", "items": ""})
                v = {"tagline": str(data.get("tagline", "")),
                     "copyright": str(data.get("copyright", "")), "cols": cols}
                b = footer_write(v)
                self._json({"ok": True, "backup": b})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)
            return
        if u.path == "/api/restart":
            r = subprocess.run(["systemctl", "--user", "restart", "entrosana-site"], capture_output=True, text=True)
            act = subprocess.run(["systemctl", "--user", "is-active", "entrosana-site"], capture_output=True, text=True).stdout.strip()
            self._json({"ok": r.returncode == 0, "service": act, "err": r.stderr[-200:]})
            return
        if u.path == "/api/backup-all":
            ts = time.strftime("%Y%m%d-%H%M%S")
            dest = BACKUPS / f"full-{ts}.tar.gz"
            r = subprocess.run(["tar", "czf", str(dest), "-C", str(SITE), "dist", "server.mjs"], capture_output=True, text=True)
            self._json({"ok": r.returncode == 0, "archive": dest.name})
            return
        self._json({"ok": False, "error": "unknown"}, 404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"entrosana-admin on 0.0.0.0:{PORT} (tailnet+loopback enforced by source-IP allowlist); token file: {TOKEN_FILE}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
