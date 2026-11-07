#!/usr/bin/env python3
"""entrosana.com · Konsole (:8393, nur Tailnet).

Seit 2026-11-05 ist entrosana.com eine Astro-Seite (~/entrosana-com), gebaut
nach dist/ und per ~/entrosana-metanet/deploy-com.sh nach Metanet geladen.
Diese Konsole löst den WordPress-Editor ab: sie bearbeitet nur Text, an
seiner Byteposition in den Quelldateien unter src/. Markup, Klassen,
Ausdrücke und Layout bleiben unberührt.

Ablauf: Feld ändern → «Speichern» schreibt die Datei und baut dist/ neu
(Vorschau auf :8394) → «Veröffentlichen» lädt dist/ nach Metanet und
committet die Änderung auf den Site-Branch (Push auf dessen Upstream).

Drei Arten von Textstellen:
  T  Text zwischen Tags in einer Vorlage (.astro, .html), auch in JSX
     innerhalb von {…}-Ausdrücken
  A  Attributwerte mit Prosa (title, description, lede, eyebrow, alt, …)
  F  Zeichenketten in doppelten Anführungszeichen im Frontmatter bzw. in
     .ts-Dateien, sofern sie wie Prosa aussehen (Leerzeichen, kein Pfad)

Nur Standardbibliothek. Start: python3 konsole/konsole.py  (KONSOLE_PORT=…)
Prüfen ohne zu schreiben: python3 konsole/konsole.py --pruefen
"""
import hashlib, html, ipaddress, os, re, shutil, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote, unquote

HOME = Path.home()
ROOT = HOME / "entrosana-com"
SRC = ROOT / "src"
DIST = ROOT / "dist"
ASTRO = ROOT / "node_modules" / ".bin" / "astro"
DEPLOY = HOME / "entrosana-metanet" / "deploy-com.sh"
UPLOAD_LOG = HOME / "entrosana-metanet" / "upload.log"
BACKUPS = HOME / "entrosana-com-backups"
LOG = HOME / ".sygnif" / "logs" / "entrosana-com-konsole.log"
PORT = int(os.environ.get("KONSOLE_PORT") or 8393)
BIND = os.environ.get("KONSOLE_BIND") or "0.0.0.0"
PREVIEW = os.environ.get("KONSOLE_PREVIEW") or "http://100.115.236.97:8394"
LIVE = "https://entrosana.com"
HUB_KONSOLE = "http://100.115.236.97:8396"
PATH_ENV = f"{HOME}/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", "")

# Was die Konsole kennt: (Schlüssel relativ zu src/, Name, Pfad in der Vorschau
# und live, Beschreibung). Die Reihenfolge ist die der Übersicht.
DATEIEN = [
    ("Seiten", [
        ("pages/index.astro", "Startseite", "/", "Kopf, zwei Dienste, Arbeitsweise, Hub, Stand, Kette"),
        ("pages/modules.astro", "Modules", "/modules/", "erstes Modul, drei Bereiche, Anfrage"),
        ("pages/service.astro", "Back office", "/service/", "Werkzeuge, Datenbild, Anbieter, Betriebsarten, Pilot"),
        ("pages/hub.astro", "Hub", "/hub/", "Aufbau, Rollen, was der Hub tut"),
        ("pages/roadmap.astro", "Roadmap", "/roadmap/", "gebaut, in Arbeit, geplant; drei Entscheide"),
        ("pages/request-access.astro", "Request access", "/request-access/", "Kontaktseite um das Formular"),
        ("pages/404.astro", "404-Seite", "/404.html", "Text bei unbekannter Adresse"),
    ]),
    ("Bausteine", [
        ("components/Footer.astro", "Fusszeile", "/", "Leitsatz, Spalten, Residenz und Sprache"),
        ("components/HubStack.astro", "Hub-Bild", "/#hub", "Beschriftung der Figur auf der Startseite"),
        ("components/DataLayers.astro", "Datenbild", "/service/#data", "zwei Modellschichten, Back office"),
        ("components/DeployTable.astro", "Betriebsarten", "/service/#deploy", "Hosted, Hybrid, On-premises"),
        ("components/RecordChain.astro", "Kette", "/#record", "Beispielzeilen der versiegelten Einträge"),
        ("layouts/Layout.astro", "Grundgerüst", "/", "Standardtitel und -beschreibung aller Seiten"),
        ("lib/site.ts", "Navigation und Auswahl", "/", "Menüpunkte, Adresse, Interessen im Formular"),
    ]),
    ("Rechtstexte", [
        ("legal/imprint.html", "Impressum", "/imprint/", "Anbieter, Kontakt, Quelle"),
        ("legal/privacy.en.html", "Privacy (EN)", "/privacy/", "Datenschutz, englisch"),
        ("legal/privacy.de.html", "Datenschutz (DE)", "/privacy/de/", "Datenschutz, deutsch"),
        ("pages/imprint.astro", "Impressum · Seitentitel", "/imprint/", "Titel und Beschreibung der Seite"),
        ("pages/privacy.astro", "Privacy · Seitentitel", "/privacy/", "Titel und Beschreibung der Seite"),
        ("pages/privacy/de.astro", "Datenschutz · Seitentitel", "/privacy/de/", "Titel und Beschreibung der Seite"),
    ]),
]
EINTRAG = {k: (name, pfad, desc) for _g, liste in DATEIEN for k, name, pfad, desc in liste}
IM_CODE = ("Formulare (ContactForm, ModuleForm), Kopfzeile (SiteNav), Statuszeile und Themenschalter "
           "stehen als Inseln in src/components/islands/*.tsx. Diese Texte ändern sich im Code, nicht hier.")

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
RAW = {"style", "script"}
ATTRS = {"title", "description", "lede", "eyebrow", "alt", "placeholder", "aria-label", "label"}
TAG_RE = re.compile(r"<(/?)([A-Za-z][\w:.-]*)")
JSX_RE = re.compile(r"<[A-Za-z]")
ATTR_NAME_RE = re.compile(r"([A-Za-z_:][\w:.-]*)\s*=\s*$")
KEY_RE = re.compile(r"([A-Za-z_]\w*)\s*[:=]\s*$")
CONST_RE = re.compile(r"\b(?:const|let|var)\s+(?:\{\s*)?([A-Za-z_]\w*)")
BR_RE = re.compile(r"<br\s*/?>", re.I)
BUILD_LOCK = threading.Lock()
LETZTER = {"wann": "", "was": "", "ok": True, "log": ""}


# ── Hilfen ──────────────────────────────────────────────────────────────────

def glatt(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def log(zeile: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {zeile}\n")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def wann(p: Path) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))
    except OSError:
        return "–"


def sicherung(p: Path) -> str:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    flach = str(p.relative_to(SRC)).replace("/", "__")
    dest = BACKUPS / f"{flach}.{ts}"
    k = 0
    while dest.exists():
        k += 1
        dest = BACKUPS / f"{flach}.{ts}-{k}"
    shutil.copy2(p, dest)
    for alt in sorted(BACKUPS.glob(f"{flach}.*"))[:-30]:
        alt.unlink()
    return dest.name


def skip_string(s: str, i: int, end: int) -> int:
    q = s[i]; j = i + 1
    while j < end:
        c = s[j]
        if c == "\\":
            j += 2; continue
        if c == q:
            return j + 1
        if c == "\n" and q != "`":
            return j          # unbeendete Zeichenkette: am Zeilenende aufhören
        j += 1
    return end


def js_unescape(t: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), t)


def js_escape(t: str) -> str:
    return t.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def enc_text(t: str) -> str:
    """Vorlagentext: Entitäten für & < > { }, Zeilenumbrüche nur als <br />."""
    teile = BR_RE.split(t)
    esc = [p.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("{", "&#123;").replace("}", "&#125;") for p in teile]
    return "<br />".join(esc)


def enc_attr(t: str) -> str:
    return html.escape(t, quote=True).replace("{", "&#123;").replace("}", "&#125;")


# ── Lesen: Textstellen mit Byteposition ────────────────────────────────────

class Vorlage:
    """Durchläuft eine Vorlage (HTML mit Astro-/JSX-Ausdrücken) und sammelt
    Textknoten (T) und Prosa-Attribute (A) mit ihren Positionen."""

    def __init__(self, s: str, start: int, end: int):
        self.s, self.i, self.end = s, start, end
        self.nodes, self.stack = [], []

    def flush(self, a: int, b: int):
        seg = self.s[a:b]
        st = seg.strip()
        if not st:
            return
        a2 = a + (len(seg) - len(seg.lstrip()))
        self.nodes.append({"kind": "T", "a": a2, "b": a2 + len(st),
                           "label": self.stack[-1] if self.stack else "text"})

    def scan_tag(self):
        s = self.s
        m = TAG_RE.match(s, self.i)
        closing, name = m.group(1) == "/", m.group(2)
        j, attrs = m.end(), []
        while j < self.end:
            c = s[j]
            if c == ">":
                j += 1; break
            if c in "\"'":
                k = s.find(c, j + 1)
                k = self.end if k < 0 else k
                am = ATTR_NAME_RE.search(s, m.end(), j)
                if am and c == '"' and not closing:
                    attrs.append((am.group(1), j + 1, k))
                j = k + 1; continue
            if c == "{":
                self.i = j; self.expression(); j = self.i; continue
            j += 1
        selfclosing = s[j - 2:j] == "/>"
        self.i = j
        return closing, name, attrs, selfclosing

    def open_element(self, name, attrs, selfclosing):
        for an, va, vb in attrs:
            if an.lower() in ATTRS and glatt(self.s[va:vb]):
                self.nodes.append({"kind": "A", "a": va, "b": vb, "label": an})
        low = name.lower()
        if low in RAW and not selfclosing:
            k = re.compile(r"</" + re.escape(name) + r"\s*>", re.I).search(self.s, self.i)
            self.i = self.end if not k else k.end()
            return
        if selfclosing or low in VOID:
            return
        self.stack.append(name)
        self.template(name)
        self.stack.pop()

    def template(self, close_name):
        s = self.s
        text_start = None
        while self.i < self.end:
            c = s[self.i]
            if c == "<":
                if s.startswith("<!--", self.i):
                    if text_start is not None:
                        self.flush(text_start, self.i); text_start = None
                    k = s.find("-->", self.i + 4)
                    self.i = self.end if k < 0 else k + 3
                    continue
                if s.startswith("<!", self.i):
                    if text_start is not None:
                        self.flush(text_start, self.i); text_start = None
                    k = s.find(">", self.i)
                    self.i = self.end if k < 0 else k + 1
                    continue
                if s.startswith("</>", self.i) or s.startswith("<>", self.i):
                    if text_start is not None:
                        self.flush(text_start, self.i); text_start = None
                    if s.startswith("</>", self.i):
                        self.i += 3
                        if close_name == "":
                            return
                        continue
                    self.i += 2
                    self.stack.append("")
                    self.template("")
                    self.stack.pop()
                    continue
                if not TAG_RE.match(s, self.i):
                    if text_start is None:
                        text_start = self.i
                    self.i += 1
                    continue
                if text_start is not None:
                    self.flush(text_start, self.i); text_start = None
                closing, name, attrs, selfclosing = self.scan_tag()
                if closing:
                    if close_name is not None and name == close_name:
                        return
                    continue
                self.open_element(name, attrs, selfclosing)
                continue
            if c == "{":
                if text_start is not None:
                    self.flush(text_start, self.i); text_start = None
                self.expression()
                continue
            if text_start is None:
                text_start = self.i
            self.i += 1
        if text_start is not None:
            self.flush(text_start, self.i)

    def expression(self):
        """Ab «{» bis zur passenden «}». JSX darin wird wieder als Vorlage gelesen."""
        s = self.s
        depth = 0
        while self.i < self.end:
            c = s[self.i]
            if c in "\"'`":
                self.i = skip_string(s, self.i, self.end); continue
            if c == "{":
                depth += 1; self.i += 1; continue
            if c == "}":
                depth -= 1; self.i += 1
                if depth <= 0:
                    return
                continue
            if c == "/" and s.startswith("//", self.i):
                k = s.find("\n", self.i); self.i = self.end if k < 0 else k; continue
            if c == "/" and s.startswith("/*", self.i):
                k = s.find("*/", self.i + 2); self.i = self.end if k < 0 else k + 2; continue
            if c == "<" and s.startswith("<>", self.i):
                self.i += 2
                self.stack.append("")
                self.template("")
                self.stack.pop()
                continue
            if c == "<" and JSX_RE.match(s, self.i):
                closing, name, attrs, selfclosing = self.scan_tag()
                if not closing:
                    self.open_element(name, attrs, selfclosing)
                continue
            self.i += 1


def js_strings(s: str, start: int, end: int):
    """[(a, b)] der Inhalte doppelt zitierter Zeichenketten, Kommentare und andere Zitate übersprungen."""
    out, j = [], start
    while j < end:
        c = s[j]
        if c == "/" and s.startswith("//", j):
            k = s.find("\n", j); j = end if k < 0 else k; continue
        if c == "/" and s.startswith("/*", j):
            k = s.find("*/", j + 2); j = end if k < 0 else k + 2; continue
        if c in "'`":
            j = skip_string(s, j, end); continue
        if c == '"':
            k = skip_string(s, j, end)
            if k - 1 > j + 1 and s[k - 1] == '"':
                out.append((j + 1, k - 1))
            j = k; continue
        j += 1
    return out


PROSA_SCHLUESSEL = {"name", "label", "tag", "what", "who", "title", "body", "gist", "why", "needs", "keys",
                    "model", "docs", "t", "eyebrow", "lede", "description", "text", "note", "summary", "alt",
                    "when", "where", "how", "hint", "placeholder", "cta"}
KEINE_SCHLUESSEL = {"state", "id", "kind", "href", "to", "key", "slug", "class", "type", "lang", "src", "rel",
                    "target", "icon", "n", "from", "import", "mode", "dir", "format"}


def prosa(v: str, key) -> bool:
    """Anzeigetext, nicht Pfad oder Kennung: mehrere Wörter, oder ein Wort unter
    einem Prosa-Schlüssel, oder ein grossgeschriebenes Wort ohne Schlüssel (Listen)."""
    v = v.strip()
    if len(v) < 3 or v.startswith(("/", "#", "?", "http", "mailto:", ".", "<", "@", "{")):
        return False
    if key in KEINE_SCHLUESSEL:
        return False
    if " " in v:
        return True
    return key in PROSA_SCHLUESSEL or (key is None and v[0].isupper())


def daten_nodes(s: str, start: int, end: int):
    nodes = []
    for a, b in js_strings(s, start, end):
        raw = s[a:b]
        vor = s[max(start, a - 60):a - 1]
        if re.search(r"\bfrom\s*$", vor) or re.search(r"\bimport\s*$", vor):
            continue
        km = KEY_RE.search(vor)
        if not prosa(js_unescape(raw), km.group(1) if km else None):
            continue
        cm = None
        for cm in CONST_RE.finditer(s, start, a):
            pass
        gruppe = "Daten"
        if cm:
            gruppe = "Vorgaben" if "{" in cm.group(0) else cm.group(1)
        nodes.append({"kind": "F", "a": a, "b": b, "label": km.group(1) if km else "Text", "gruppe": gruppe})
    return nodes


def lies(key: str):
    """(Quelltext, Stellen, Gruppen) einer Datei. Stellen tragen text = Anzeigeform."""
    p = SRC / key
    s = p.read_text(encoding="utf-8")
    nodes = []
    t_start, t_end = 0, len(s)
    if key.endswith(".ts"):
        nodes = daten_nodes(s, 0, len(s))
        t_start = t_end = 0
    elif key.endswith(".astro") and s.startswith("---"):
        fm_end = s.find("\n---", 3)
        if fm_end >= 0:
            nodes += daten_nodes(s, 3, fm_end)
            t_start = s.find("\n", fm_end + 1) + 1
    if t_start < t_end:
        v = Vorlage(s, t_start, t_end)
        v.template(None)
        nodes += v.nodes
    nodes.sort(key=lambda n: n["a"])
    for i, n in enumerate(nodes):
        n["i"] = i
        raw = s[n["a"]:n["b"]]
        if n["kind"] == "T":
            n["text"] = glatt(html.unescape(raw))
        elif n["kind"] == "A":
            n["text"] = glatt(html.unescape(raw))
        else:
            n["text"] = js_unescape(raw)
    return s, nodes, gruppen(s, nodes, t_start)


def abschnitte(s: str, start: int):
    """[(a, b, titel)] der obersten <section>-Blöcke der Vorlage."""
    out, tiefe, offen = [], 0, None
    for m in re.finditer(r"</?section\b[^>]*>", s[start:]):
        pos = start + m.start()
        if m.group(0).startswith("</"):
            tiefe -= 1
            if tiefe == 0 and offen is not None:
                out.append((offen, pos + len(m.group(0))))
                offen = None
        else:
            if tiefe == 0:
                offen = pos
            tiefe += 1
    return out


def gruppen(s: str, nodes: list, t_start: int):
    """[{titel, zu, stellen}] in Leserichtung: Kopf, Daten, Abschnitte."""
    secs = abschnitte(s, t_start)
    kopf, daten, rest = [], {}, {k: [] for k in range(len(secs))}
    uebrig = []
    for n in nodes:
        if n["kind"] == "F":
            daten.setdefault(n["gruppe"], []).append(n)
            continue
        for k, (a, b) in enumerate(secs):
            if a <= n["a"] < b:
                rest[k].append(n); break
        else:
            (kopf if n["a"] < (secs[0][0] if secs else len(s) + 1) else uebrig).append(n)
    out = []
    if kopf:
        out.append({"titel": "Kopf der Seite · Titel, Beschreibung, Einstieg" if secs else "Texte",
                    "zu": False, "stellen": kopf})
    for name, liste in daten.items():
        out.append({"titel": f"Daten · {name}", "zu": False, "stellen": liste})
    for k, liste in rest.items():
        if not liste:
            continue
        erster = next((n["text"] for n in liste if n["kind"] == "T"), "")
        titel = erster[:48] + ("…" if len(erster) > 48 else "") if erster else f"Abschnitt {k + 1}"
        out.append({"titel": titel, "zu": False, "stellen": liste})
    if uebrig:
        out.append({"titel": "Weitere Texte", "zu": False, "stellen": uebrig})
    return out


# ── Schreiben ──────────────────────────────────────────────────────────────

def pruefe_text(kind: str, t: str):
    if kind in ("T", "A"):
        rest = BR_RE.sub("", t) if kind == "T" else t
        if "<" in rest or ">" in rest:
            raise ValueError("Spitze Klammern sind nicht erlaubt; Zeilenumbrüche nur als <br>")


def schreibe(key: str, neu: dict, h: str):
    """neu = {index: text}. Gibt die Liste der geänderten Stellen zurück."""
    p = SRC / key
    s, nodes, _g = lies(key)
    if h and sha(s.encode("utf-8")) != h:
        raise ValueError("Die Datei hat sich seit dem Laden geändert. Neu laden und nochmals ändern.")
    geaendert = []
    out = s
    for n in reversed(nodes):
        if str(n["i"]) not in neu:
            continue
        t = neu[str(n["i"])].replace("\r\n", "\n").replace("\r", "\n")
        if n["kind"] in ("T", "A"):
            t = glatt(t)
        else:
            t = t.strip("\n")
        if t == n["text"]:
            continue
        if not t and n["kind"] != "F":
            raise ValueError(f"Feld {n['i'] + 1} ({n['label']}) darf nicht leer sein; sonst verschwindet die Stelle.")
        pruefe_text(n["kind"], t)
        enc = enc_text(t) if n["kind"] == "T" else enc_attr(t) if n["kind"] == "A" else js_escape(t)
        out = out[:n["a"]] + enc + out[n["b"]:]
        geaendert.append((n["label"], n["text"], t))
    if not geaendert:
        return []
    sicherung(p)
    p.write_text(out, encoding="utf-8")
    log(f"{key}: {len(geaendert)} Stellen geändert: " + "; ".join(f"{l}: {a[:40]!r} -> {b[:40]!r}" for l, a, b in geaendert[:6]))
    return geaendert


# ── Bauen, Veröffentlichen, Git ────────────────────────────────────────────

def lauf(cmd, cwd=ROOT, timeout=180):
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "PATH": PATH_ENV, "HOME": str(HOME)})
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "Zeitüberschreitung"
    except OSError as e:
        return 127, str(e)


def git(*args, timeout=60):
    return lauf(["git", *args], timeout=timeout)


def git_stand():
    rc, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    rc2, up = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    rc3, st = git("status", "--porcelain", "--", "src")
    offen = [l[3:] for l in st.splitlines() if l.strip()] if rc3 == 0 else []
    rc4, ab = git("rev-list", "--left-right", "--count", "HEAD...@{u}") if rc2 == 0 else (1, "")
    ahead = ab.split()[0] if rc4 == 0 and ab.split() else "?"
    return {"branch": branch if rc == 0 else "?", "upstream": up if rc2 == 0 else "", "offen": offen, "ahead": ahead}


def bauen():
    if not ASTRO.exists():
        return 127, f"{ASTRO} fehlt"
    rc, out = lauf([str(ASTRO), "build"])
    zeilen = [l for l in out.splitlines() if l.strip()]
    return rc, "\n".join(zeilen[-25:])


def merke(was, ok, text):
    LETZTER.update({"wann": time.strftime("%Y-%m-%d %H:%M:%S"), "was": was, "ok": ok, "log": text})
    log(f"{was}: {'ok' if ok else 'FEHLER'}")


def vorschau_bauen():
    if not BUILD_LOCK.acquire(blocking=False):
        return False, "Ein Bau läuft gerade. Gleich nochmals versuchen."
    try:
        rc, out = bauen()
        merke("Vorschau gebaut", rc == 0, out)
        return rc == 0, out
    finally:
        BUILD_LOCK.release()


def veroeffentlichen(hinweis=""):
    if not BUILD_LOCK.acquire(blocking=False):
        return False, "Ein Bau läuft gerade. Gleich nochmals versuchen."
    try:
        teile = []
        rc, out = bauen()
        teile.append("== astro build\n" + out)
        if rc != 0:
            merke("Veröffentlichen", False, "\n".join(teile))
            return False, "\n".join(teile)
        rc, out = lauf([str(DEPLOY)], cwd=DEPLOY.parent, timeout=300)
        try:
            out += "\n" + UPLOAD_LOG.read_text().strip().splitlines()[-1]
        except (OSError, IndexError):
            pass
        teile.append("== deploy-com.sh\n" + out)
        if rc != 0:
            merke("Veröffentlichen", False, "\n".join(teile))
            return False, "\n".join(teile)
        st = git_stand()
        if st["offen"]:
            git("add", "-A", "--", "src")
            msg = "texte: " + ", ".join(Path(f).name for f in st["offen"][:6]) + (" …" if len(st["offen"]) > 6 else "") + " (Konsole)"
            if hinweis:
                msg += "\n\n" + hinweis
            rc, out = git("commit", "-q", "-m", msg)
            teile.append("== git commit\n" + (out or msg.splitlines()[0]))
            if st["upstream"] and "/" in st["upstream"]:
                remote, zweig = st["upstream"].split("/", 1)
                rc, out = git("push", "-q", remote, f"HEAD:{zweig}", timeout=120)
                teile.append(f"== git push {remote} HEAD:{zweig}\n" + (out or ("ok" if rc == 0 else f"rc={rc}")))
            else:
                teile.append("== git push\nkein Upstream gesetzt, nicht gepusht")
        else:
            teile.append("== git\nnichts zu committen (keine offenen Änderungen unter src/)")
        merke("Veröffentlicht", True, "\n".join(teile))
        return True, "\n".join(teile)
    finally:
        BUILD_LOCK.release()


# ── Seiten ─────────────────────────────────────────────────────────────────

CSS = """*{box-sizing:border-box}
body{margin:0;background:#1B1E24;color:#E9EBE7;font-family:Calibri,Carlito,'Segoe UI',sans-serif;padding:2rem}
.wrap{max-width:78rem;margin:0 auto}
h1,h2{font-weight:600;letter-spacing:-.02em} h1{font-size:1.9rem;margin:.2rem 0 .6rem} h2{font-size:1.2rem;margin:2.2rem 0 .6rem}
h1 span{color:#2BD4E8}
.mono{font-family:Inconsolata,Consolas,ui-monospace,Menlo,monospace;font-size:.84rem;color:#8F95A1}
a{color:#2BD4E8;text-decoration:none} a:hover{text-decoration:underline}
table{width:100%;border-collapse:collapse;margin-top:.5rem}
td,th{padding:.55em .7em;border-bottom:1px solid #323843;vertical-align:top;text-align:left}
th{color:#8F95A1;font-weight:400;font-size:.82rem}
td b{font-size:1.02rem}
.btn{display:inline-block;background:#2BD4E8;color:#071316;border:1px solid #2BD4E8;border-radius:999px;padding:.5em 1.1em;font:inherit;font-weight:600;cursor:pointer;min-height:44px;line-height:1.6}
.btn.ghost{background:none;color:#C6CAD1;border-color:#5A6273}
.btn.warn{background:none;color:#DC7A6E;border-color:#7a4a44}
.note{color:#8F95A1;font-size:.9rem;max-width:72ch;line-height:1.55}
.err{color:#DC7A6E} .ok{color:#35B36B}
.desc{color:#8F95A1;font-size:.86rem;line-height:1.45} .act{white-space:nowrap}
.stand{display:grid;gap:.35rem;margin:1rem 0 1.4rem;padding:1rem 1.2rem;border:1px solid #323843;border-radius:12px;background:rgba(255,255,255,.02)}
.stand .mono{color:#C6CAD1}
.leiste{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center;margin:.8rem 0}
pre{white-space:pre-wrap;word-break:break-word;font-family:Inconsolata,Consolas,ui-monospace,monospace;font-size:.82rem;color:#C6CAD1;background:#101318;border:1px solid #323843;border-radius:8px;padding:.8rem 1rem;max-height:24rem;overflow:auto}
textarea,input[type=text]{width:100%;background:#101318;color:#E9EBE7;border:1px solid #323843;border-radius:8px;padding:.5em .7em;font:inherit;font-size:.95rem}
textarea{min-height:3.2rem;resize:vertical;line-height:1.45}
.f{display:grid;grid-template-columns:5.4rem minmax(0,1fr);gap:.7rem;align-items:start;margin:.3rem 0;padding-bottom:.3rem;border-bottom:1px solid #262b33}
.f .k{color:#8F95A1;font-family:Inconsolata,Consolas,ui-monospace,monospace;font-size:.72rem;padding-top:.55em;word-break:break-all}
.f.geaendert .k{color:#2BD4E8}
.grp{border:1px solid #262b33;border-radius:10px;margin:.5rem 0;background:rgba(255,255,255,.015)}
.grp>summary{cursor:pointer;padding:.55rem .8rem;font-size:.92rem;color:#C6CAD1;list-style:none}
.grp>summary::-webkit-details-marker{display:none}
.grp>summary::before{content:"▸ ";color:#2BD4E8}
.grp[open]>summary::before{content:"▾ "}
.grp>summary .n{float:right;color:#8F95A1;font-size:.8rem}
.grp>div{padding:.3rem .8rem .7rem}
.zwei{display:grid;grid-template-columns:minmax(24rem,42%) minmax(0,1fr);gap:1rem;align-items:start}
.felder{max-height:calc(100vh - 14rem);overflow:auto;padding-right:.3rem}
.vorschau{position:sticky;top:1rem}
.vorschau iframe{width:100%;height:calc(100vh - 14rem);border:1px solid #323843;border-radius:10px;background:#1B1E24}
.bar{position:sticky;bottom:0;background:#1B1E24;border-top:1px solid #323843;padding:.8rem 0;margin-top:1rem;display:flex;flex-wrap:wrap;gap:.6rem;align-items:center}
@media (max-width:900px){
  body{padding:1rem .9rem}
  .zwei{grid-template-columns:minmax(0,1fr)}
  .felder{max-height:none;overflow:visible}
  .vorschau{position:static} .vorschau iframe{height:60vh}
  table,tbody,tr,td{display:block;width:100%}
  thead{display:none}
  tr{border-bottom:1px solid #323843;padding:.6rem 0} tr:last-child{border-bottom:0}
  td{border:0;padding:.15rem 0} td:empty{display:none}
  .act{white-space:normal;display:inline-block;padding:.5rem 0;min-height:44px}
  .f{grid-template-columns:4.2rem minmax(0,1fr)}
}
"""


def seite(titel: str, body: str) -> str:
    return (f"<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'><title>{html.escape(titel)}</title>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><meta name='robots' content='noindex'>"
            f"<style>{CSS}</style></head><body><div class='wrap'>{body}</div></body></html>")


def protokoll_block(offen=False):
    if not LETZTER["wann"]:
        return ""
    farbe = "ok" if LETZTER["ok"] else "err"
    return (f"<details class='grp'{' open' if offen or not LETZTER['ok'] else ''}><summary><b class='{farbe}'>"
            f"{html.escape(LETZTER['was'])}</b> <span class='n'>{LETZTER['wann']}</span></summary>"
            f"<div><pre>{html.escape(LETZTER['log'] or '(keine Ausgabe)')}</pre></div></details>")


def uebersicht(msg="", err=""):
    st = git_stand()
    try:
        up = UPLOAD_LOG.read_text().strip().splitlines()[-1]
    except (OSError, IndexError):
        up = "noch nie"
    offen = st["offen"]
    zeilen = (
        f"<div class='mono'>Live: <a href='{LIVE}' target='_blank'>entrosana.com</a> · zuletzt hochgeladen {wann(UPLOAD_LOG)} ({html.escape(up)})</div>"
        f"<div class='mono'>Vorschau: <a href='{PREVIEW}/' target='_blank'>{PREVIEW.replace('http://', '')}</a> · gebaut {wann(DIST / 'index.html')}</div>"
        f"<div class='mono'>Git: {html.escape(st['branch'])}"
        + (f" → {html.escape(st['upstream'])}, {html.escape(str(st['ahead']))} Commits voraus" if st["upstream"] else "")
        + (f" · <span class='err'>{len(offen)} Datei(en) geändert, noch nicht veröffentlicht: {html.escape(', '.join(Path(f).name for f in offen))}</span>"
           if offen else " · <span class='ok'>alles veröffentlicht</span>") + "</div>"
    )
    tabellen = ""
    for gname, liste in DATEIEN:
        rows = ""
        for key, name, pfad, desc in liste:
            try:
                _s, nodes, _g = lies(key)
                n = len(nodes)
            except OSError:
                n = 0
            mark = " <span class='err'>●</span>" if key in offen or any(o.endswith(key) for o in offen) else ""
            rows += (f"<tr><td><b>{html.escape(name)}</b>{mark}<br><span class='mono'>{html.escape(key)}</span></td>"
                     f"<td class='desc'>{html.escape(desc)}</td><td class='mono'>{n} Felder</td>"
                     f"<td class='act'><a href='/texte/{quote(key)}'>Texte bearbeiten</a></td>"
                     f"<td class='act'><a href='{LIVE}{pfad}' target='_blank'>live</a> · <a href='{PREVIEW}{pfad}' target='_blank'>Vorschau</a></td></tr>")
        tabellen += f"<h2>{gname}</h2><table>{rows}</table>"
    body = (
        "<h1>entro<span>sana</span>.com · Konsole</h1>"
        "<p class='note'>Die Texte der Seite, an ihrer Stelle in den Quelldateien. Speichern baut die Vorschau; "
        "Veröffentlichen lädt den Stand nach Metanet und schreibt ihn ins Git.</p>"
        + (f"<p class='ok'>{html.escape(msg)}</p>" if msg else "")
        + (f"<p class='err'>{html.escape(err)}</p>" if err else "")
        + f"<div class='stand'>{zeilen}</div>"
        "<div class='leiste'>"
        "<form method='post' action='/veroeffentlichen'><button class='btn'>Veröffentlichen</button></form>"
        "<form method='post' action='/vorschau'><button class='btn ghost'>Vorschau neu bauen</button></form>"
        f"<a class='btn ghost' href='{PREVIEW}/' target='_blank'>Vorschau öffnen</a>"
        f"<a class='btn ghost' href='{HUB_KONSOLE}' target='_blank'>Hub-Konsole :8396</a>"
        "<a class='btn ghost' href='/protokoll'>Protokoll</a>"
        "</div>"
        + protokoll_block()
        + tabellen
        + f"<h2>Im Code</h2><p class='note'>{IM_CODE}</p>"
    )
    return seite("entrosana.com · Konsole", body)


def editor(key: str, msg="", err=""):
    name, pfad, desc = EINTRAG[key]
    s, nodes, grp = lies(key)
    h = sha(s.encode("utf-8"))
    st = git_stand()
    offen = any(o.endswith(key) for o in st["offen"])

    def feld(n):
        text = n["text"]
        kurz = len(text) <= 60 and "\n" not in text
        rows = max(2, min(10, len(text) // 70 + 1))
        eingabe = (f"<input type=text name='t{n['i']}' value=\"{html.escape(text, quote=True)}\">" if kurz else
                   f"<textarea name='t{n['i']}' rows='{rows}'>{html.escape(text)}</textarea>")
        return f"<div class='f'><div class='k'>{html.escape(n['label'])}</div><div>{eingabe}</div></div>"

    bloecke = ""
    for g in grp:
        bloecke += (f"<details class='grp'{'' if g['zu'] else ' open'}><summary><b>{html.escape(g['titel'])}</b>"
                    f"<span class='n'>{len(g['stellen'])} Felder</span></summary>"
                    f"<div>{''.join(feld(n) for n in g['stellen'])}</div></details>")
    if not nodes:
        bloecke = "<p class='note'>In dieser Datei gibt es keine Textstellen, die hier bearbeitbar wären.</p>"
    basis, _, frag = pfad.partition("#")
    vorschau = f"{PREVIEW}{basis}?v={int(time.time())}" + (f"#{frag}" if frag else "")
    body = (
        f"<p><a href='/'>&larr; Übersicht</a></p><h1>{html.escape(name)}</h1>"
        f"<p class='mono'>{html.escape(key)} · {len(nodes)} Textstellen · {html.escape(desc)}"
        + (" · <span class='err'>geändert, noch nicht veröffentlicht</span>" if offen else "") + "</p>"
        + (f"<p class='ok'>{html.escape(msg)}</p>" if msg else "")
        + (f"<p class='err'>{html.escape(err)}</p>" if err else "")
        + protokoll_block(offen=bool(err))
        + f"<form method='post' action='/texte/{quote(key)}' id='form'>"
        + f"<input type='hidden' name='h' value='{h}'>"
        + "<div class='zwei'>"
        + f"<div class='felder'>{bloecke}</div>"
        + f"<div class='vorschau'><iframe src='{html.escape(vorschau)}' title='Vorschau'></iframe>"
        + f"<p class='mono'>Vorschau von {html.escape(PREVIEW)}{html.escape(basis)} · nach dem Speichern neu geladen</p></div>"
        + "</div>"
        + "<div class='bar'>"
        + "<button class='btn' name='aktion' value='speichern'>Speichern (Vorschau bauen)</button> "
        + "<button class='btn' name='aktion' value='veroeffentlichen'>Speichern und veröffentlichen</button> "
        + f"<a class='btn ghost' href='{LIVE}{pfad}' target='_blank'>Live ansehen</a> "
        + "<a class='btn ghost' href='/'>Zurück</a>"
        + (" <button class='btn warn' name='aktion' value='zuruecksetzen' formnovalidate "
           "onclick=\"return confirm('Diese Datei auf den letzten Git-Stand zurücksetzen? Ungespeicherte und gespeicherte, noch nicht veröffentlichte Änderungen gehen verloren.')\">Auf Git-Stand zurücksetzen</button>" if offen else "")
        + "</div></form>"
        "<script>"
        "var f=document.getElementById('form'),dirty=false;"
        "f.addEventListener('input',function(e){dirty=true;var w=e.target.closest('.f');if(w)w.classList.add('geaendert');});"
        "f.addEventListener('submit',function(){dirty=false;});"
        "window.addEventListener('beforeunload',function(e){if(dirty){e.preventDefault();e.returnValue='';}});"
        "</script>"
    )
    return seite(f"{name} · entrosana.com Konsole", body)


def protokoll():
    try:
        zeilen = LOG.read_text(encoding="utf-8").splitlines()[-200:]
    except OSError:
        zeilen = []
    return seite("Protokoll · entrosana.com Konsole",
                 "<p><a href='/'>&larr; Übersicht</a></p><h1>Protokoll</h1>"
                 f"<p class='mono'>{html.escape(str(LOG))} · letzte {len(zeilen)} Zeilen</p>"
                 + protokoll_block(offen=True)
                 + f"<pre>{html.escape(chr(10).join(zeilen) or '(leer)')}</pre>")


# ── HTTP ───────────────────────────────────────────────────────────────────

class H(BaseHTTPRequestHandler):
    server_version = "entrosana-com-konsole"

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Robots-Tag", "noindex")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _weiter(self, ziel):
        self._send(303, b"", extra={"Location": ziel})

    def _src_ok(self):
        # Nur Loopback und das Tailscale-Netz (100.64.0.0/10): wer dort ist,
        # hat sich bei Tailscale ausgewiesen (Entscheid des Eigentümers 2026-09-08).
        ip = self.client_address[0]
        if ip in ("127.0.0.1", "::1"):
            return True
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10")
        except ValueError:
            return False

    def _form(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace")
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def do_GET(self):
        if not self._src_ok():
            return self._send(403, "nur im Tailnet", "text/plain; charset=utf-8")
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/healthz":
            return self._send(200, "ok", "text/plain; charset=utf-8")
        if u.path == "/":
            return self._send(200, uebersicht(q.get("m", ""), q.get("e", "")))
        if u.path == "/protokoll":
            return self._send(200, protokoll())
        m = re.match(r"^/texte/(.+)$", u.path)
        if m:
            key = unquote(m.group(1))
            if key not in EINTRAG:
                return self._send(404, "unbekannte Datei", "text/plain; charset=utf-8")
            try:
                return self._send(200, editor(key, q.get("m", ""), q.get("e", "")))
            except OSError as e:
                return self._send(500, f"Datei nicht lesbar: {e}", "text/plain; charset=utf-8")
        self._send(404, "nicht gefunden", "text/plain; charset=utf-8")

    def do_POST(self):
        if not self._src_ok():
            return self._send(403, "nur im Tailnet", "text/plain; charset=utf-8")
        u = urlparse(self.path)
        form = self._form()
        if u.path == "/vorschau":
            ok, out = vorschau_bauen()
            return self._weiter("/?" + ("m=Vorschau+gebaut" if ok else "e=" + quote("Bau fehlgeschlagen, siehe Protokoll")))
        if u.path == "/veroeffentlichen":
            ok, out = veroeffentlichen()
            return self._weiter("/?" + ("m=" + quote("Veröffentlicht: live und im Git") if ok else "e=" + quote("Veröffentlichen fehlgeschlagen, siehe Protokoll")))
        m = re.match(r"^/texte/(.+)$", u.path)
        if not m:
            return self._send(404, "nicht gefunden", "text/plain; charset=utf-8")
        key = unquote(m.group(1))
        if key not in EINTRAG:
            return self._send(404, "unbekannte Datei", "text/plain; charset=utf-8")
        zurueck = f"/texte/{quote(key)}?"
        aktion = form.get("aktion", "speichern")
        if aktion == "zuruecksetzen":
            rc, out = git("checkout", "--", f"src/{key}")
            if rc != 0:
                return self._weiter(zurueck + "e=" + quote("Zurücksetzen fehlgeschlagen: " + out[:200]))
            log(f"{key}: auf Git-Stand zurückgesetzt")
            ok, out = vorschau_bauen()
            return self._weiter(zurueck + ("m=" + quote("Zurückgesetzt, Vorschau neu gebaut") if ok else "e=" + quote("Zurückgesetzt, aber der Bau scheiterte")))
        neu = {k[1:]: v for k, v in form.items() if k.startswith("t") and k[1:].isdigit()}
        try:
            geaendert = schreibe(key, neu, form.get("h", ""))
        except ValueError as e:
            return self._weiter(zurueck + "e=" + quote(str(e)))
        if aktion == "veroeffentlichen":
            ok, out = veroeffentlichen(f"{len(geaendert)} Stellen in {key}" if geaendert else "")
            if ok:
                return self._weiter(zurueck + "m=" + quote(f"{len(geaendert)} Stellen gespeichert und veröffentlicht"))
            return self._weiter(zurueck + "e=" + quote("Gespeichert, aber Veröffentlichen fehlgeschlagen, siehe unten"))
        if not geaendert:
            return self._weiter(zurueck + "m=" + quote("Nichts geändert"))
        ok, out = vorschau_bauen()
        if ok:
            return self._weiter(zurueck + "m=" + quote(f"{len(geaendert)} Stellen gespeichert, Vorschau neu gebaut"))
        return self._weiter(zurueck + "e=" + quote("Gespeichert, aber der Bau scheiterte; Fehler unten. Zurücksetzen stellt den letzten Git-Stand wieder her."))

    def log_message(self, fmt, *args):
        pass


def pruefen():
    """Liest jede Datei, zeigt Stellen und prüft, dass unveränderte Texte die Datei nicht anfassen."""
    fehler = 0
    for gname, liste in DATEIEN:
        for key, name, pfad, desc in liste:
            s, nodes, grp = lies(key)
            arten = {k: sum(1 for n in nodes if n["kind"] == k) for k in "TAF"}
            # Stellen dürfen sich nicht überlappen und keinen Tag-Anfang enthalten
            ende = -1
            for n in nodes:
                roh = s[n["a"]:n["b"]]
                if n["a"] < ende or (n["kind"] == "T" and ("<" in roh or "{" in roh)):
                    print(f"  !! {key} Stelle {n['i']} ({n['label']}): {roh[:60]!r}")
                    fehler += 1
                ende = n["b"]
            print(f"{key}: {len(nodes)} Stellen (T {arten['T']}, A {arten['A']}, F {arten['F']}), {len(grp)} Gruppen: "
                  + " | ".join(g["titel"][:28] for g in grp))
            for n in nodes[:3]:
                print(f"    {n['kind']} {n['label']:<12} {n['text'][:70]!r}")
    print("Fehler:", fehler)
    return fehler


if __name__ == "__main__":
    if "--pruefen" in sys.argv:
        sys.exit(1 if pruefen() else 0)
    srv = ThreadingHTTPServer((BIND, PORT), H)
    print(f"entrosana.com Konsole auf http://{BIND}:{PORT} · Quellen {SRC} · Vorschau {PREVIEW}", flush=True)
    log(f"Start auf {BIND}:{PORT}")
    srv.serve_forever()
