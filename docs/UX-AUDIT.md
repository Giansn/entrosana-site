# UX-Audit entrosana.com → Prototyp

Stand 2026-10-16. Grundlage: Live-Seite entrosana.com (WordPress-Theme „entrosana“), alle Seiten bei 1440 px und 390 px, hell und dunkel, im Browser geprüft.
Der Prototyp in diesem Repo übernimmt **Inhalt und Marke der Live-Seite** (Graphit/Cyan, Spiral-Marke, Inconsolata) und ändert Struktur, Führung und Technik. Live bleibt unverändert, bis der Eigentümer freigibt.

## Befunde und Änderungen

| # | Befund (live) | Änderung (Prototyp) | Warum |
|---|---|---|---|
| 1 | Drei verschiedene Hauptaktionen: Hero „Contribute“ (Beitragende), Kopf „Request access“, Schluss „Request pilot access“ | Eine Hauptaktion überall: **Request pilot access**. Nebenaktion: „Try the first module“ | Zielgruppe sind Schulen/Organisationen; Beitragende haben ihren Weg im Hub |
| 2 | Ein Bereich, vier Namen: Nav „Service“, Eyebrow „Tools“, H1 „Collaborative design“, Titel „Back-office tooling“ | Überall **Back office** (URL `/service/` bleibt) | Ein Begriff pro Bereich, sonst sucht man zweimal |
| 3 | Nav-Punkt „Deploy“ springt auf einen Anker einer anderen Seite; Roadmap nur im Fliesstext verlinkt | Nav: Back office · Modules · Hub · **Roadmap**. „Where it runs“ im Footer | Der ehrliche Stand ist Kernbotschaft und gehört in die Navigation |
| 4 | Startseite 6362 px (Desktop) / 7595 px (Mobil); Zwei-Säulen-Erklärung 3×, „sealed record“ 4× erklärt | 4559 px / 6576 px (−28 % / −13 %), jede Aussage einmal | Weniger Wiederholung, schneller zur Entscheidung |
| 5 | „Sealed record“ wird nur behauptet | Interaktive **Illustration**: drei Einträge, echte SHA-256-Kette; „Rewrite entry 0142“ → Prüfung schlägt ab diesem Eintrag fehl | Abstraktes Kernversprechen wird in 5 Sekunden verständlich („shown rather than asserted“) |
| 6 | Mobil: Hauptaktion erst nach ~900 px | Hauptaktion im ersten Bildschirm | Mobil entscheidet der erste Screen |
| 7 | Immer dunkel, Systemeinstellung ignoriert (live mit Aufhell-Workaround für helle Büro-Monitore); Umschalter „◐“ ohne Zustand | Folgt der **Systemeinstellung**; Umschalter Sonne/Mond mit `aria-pressed`, Wahl gespeichert (gleicher Schlüssel wie live) | Ursache statt Workaround; Zustand für Screenreader |
| 8 | Schrift geräteabhängig (Calibri-Stack: Mac/iOS zeigen San Francisco, Android Roboto) | **Carlito** selbst gehostet (metrisch identisch zu Calibri); Lesetext 16–18 px | Gleiches Schriftbild überall; Carlito wirkt klein, daher grösser |
| 9 | Tabs verstecken 2/3 von je drei kurzen Absätzen (Modul-Bereiche, Hub-Beispiele) | Alle drei sichtbar nebeneinander | Kurze Inhalte scannt man, statt zu klicken |
| 10 | Module: zwei identische Formulare in zwei Modals, Sprunglink + zweiter Klick; sofort nutzbares Modul ganz unten | **Ein** Inline-Formular mit Wahl Request/Propose; „Available now“ direkt unter dem Seitenkopf | Weniger Klicks; das Nützlichste zuerst |
| 11 | Kontakt: „Interested in“ vorbelegt mit „Service · accounting“; Pilot-Erwartungen unter dem Formular | Platzhalter + Pflichtfeld; Aufrufe aus der Seite wählen per `?interest=` vor; Erwartungen **neben** dem Formular | Keine versehentliche Auswahl; Vertrauen vor dem Absenden |
| 12 | Karte in Karte in Karte (Hub-Abschnitt Startseite) | Flach; Hub als Schichten-Grafik (Tools/Modules → Hub → Record) | Verschachtelung ohne Bedeutung kostet Orientierung |
| 13 | Leere Sektion vor dem Footer | Entfernt | – |
| 14 | Hub „Who it’s for“: Text zu „Parents & Teachers“ beschreibt „self-directed and academic learners“; Datensicherheit mit Scherz („solar-flare resistant…“) | Abschnitt aus den stimmigen Beispiel-Texten (Lernende/Eltern/Lehrpersonen) gebaut; Scherz entfernt, Link zum Datenschutz | Passt zum Titel; bei Datensicherheit kein Witz |
| 15 | „online & on place“ (Germanismus) neben „on site“ | Überall „on site“ | Einheitlich, korrektes Englisch |
| 16 | Betriebsmodelle als Box-Grafik | Echte Tabelle (mobil als beschriftete Blöcke) + drei Karten | Vergleichbar, für Screenreader lesbar |
| 17 | Status-Labels uneinheitlich | Chips mit Form + Text + Farbe: built · in development · planned · concept | Status nie nur über Farbe |
| 18 | Barrierefreiheit | Skip-Link, `aria-current`, sichtbarer Fokus, alle Textpaare ≥ 4.5:1 (beide Themes), Bedienelemente ≥ 3:1, Klickflächen ≥ 44 px, Formular-Status als Live-Region | WCAG 2.2 AA |
| 19 | 5 CSS-Dateien (~112 KB) mit Korrekturschichten, render-blockierend | Astro-gebündeltes CSS; JS nur in Preact-Islands (~11 KB gzip); Prefetch beim Überfahren von Links | Ladezeit ist UX |
| 20 | Roadmap ohne Überblick | „At a glance“-Liste + Sprungleiste im Seitenkopf | Stand in 10 Sekunden |

### Technik (dieses Repo)
- **Preact-Islands** (Entscheid 2026-10-16): Kopfzeile/Menü/Theme `client:load`, Record-Illustration `client:visible`, Formulare `client:idle`/`client:visible`. Alles andere ist statisches HTML ohne JS. Ohne JS bleibt alles nutzbar (Menü offen, Formulare öffnen das Mailprogramm).
- **Formulare ohne Backend**: Ohne `PUBLIC_CONTACT_ENDPOINT` öffnet sich das Mailprogramm mit ausgefüllter Nachricht; der Text bleibt auf der Seite. Mit Endpoint (gleiches JSON wie `/wp-json/entrosana/v1/contact`) wird direkt gesendet.
- **GitHub-Pages-Kopie war kaputt** (CSS 404, fehlender Base-Path) → Workflow übergibt den Base-Path.
- Alte Routen (`/tools`, `/learn`, `/hosted`, `/hybrid`, `/on-premises`) leiten weiter; URLs mit Schrägstrich wie live (`/service/`); 404-Seite.
- Rechtstexte (Impressum, Datenschutz EN/DE) **wortgleich** von live übernommen (`src/content/legal/`).

## Offene Punkte für den Eigentümer
1. **Hub-Status widersprüchlich**: Roadmap „Hub platform · concept“ vs. Hub-Seite „The console · in development, sign-in built“. Beide Texte sind unverändert übernommen; bitte eine Aussage wählen.
2. **Datenschutz** verweist auf „processing register (the section at the end of this statement)“ — der Abschnitt fehlt (live ebenso).
3. **Datenschutz beschreibt die Auslieferung über Cloudflare an den eigenen Server.** Wird der Prototyp anders gehostet (z. B. GitHub Pages), muss Abschnitt 1 angepasst werden.
4. **Kontakt-Endpoint** festlegen (WP-Endpoint mit CORS, oder `/request` im Hub), sonst bleibt der Mail-Fallback.
5. **Hub-Anmeldung**: Bug gefunden und behoben in [Giansn/entrosana-app#1](https://github.com/Giansn/entrosana-app/pull/1) (Altersschalter unsichtbar + Absturz beim Absenden).
