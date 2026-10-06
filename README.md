# VeSync mit Cosori Lite 3.8L (CAF-LI401S)

Inoffizielle Kopie der Home-Assistant-Integration **VeSync** (Core 2026.9.4), die die eingebaute Integration ersetzt, bis der Cosori Lite 3.8L offiziell unterstützt wird.

*Unofficial copy of the Home Assistant core `vesync` integration (2026.9.4) that overrides the built-in one and adds the Cosori Lite 3.8L (CAF-LI401S) air fryer, until support lands upstream.*

## Grundlage

- Bibliothek: [slu125/pyvesync `v3.4.3.dev550`](https://github.com/slu125/pyvesync/releases/tag/v3.4.3.dev550) = [webdjoe/pyvesync#503](https://github.com/webdjoe/pyvesync/pull/503) (Umbau der Fritteusen) + [#550](https://github.com/webdjoe/pyvesync/pull/550) (CAF-LI401S) + `dev`, dazu die Vorheiz-Erkennung beim LI401S und eine Abfrage des echten Zustands nach dem Übertragen eines Programms.
- Integration: `homeassistant/components/vesync` aus Core 2026.9.4, angepasst an diesen pyvesync-Stand.

## Entitäten für Heißluftfritteusen

| Entität | Inhalt |
|---|---|
| Sensor Kochstatus | Standby, Vorheizen, Kochen, Fertig, … |
| Sensor Garmodus | Manuell, Hähnchen, Pommes, Bacon, Steak, Gemüse, Warmhalten |
| Sensor Restzeit, Fertig um | Restzeit (Vorheizen oder Garen) und Endzeitpunkt |
| Sensor aktuelle/eingestellte Temperatur, eingestellte Zeit | wie in der eingebauten Integration (Zeiten jetzt in Sekunden, Anzeige in Minuten) |
| Binärsensor In Betrieb | an während Vorheizen und Garen |
| Button Garen beenden | beendet das laufende Programm |
| Programm Garmodus / Temperatur / Dauer + Button Garprogramm übertragen | stellt ein Programm bereit |
| Aktion `vesync.stage_cook_program` | wie der Button, mit `mode`, `temperature`, `duration` (Minuten) |

**Der CAF-LI401S lässt sich nicht aus der Cloud starten.** Ein übertragenes Programm wird nur bereitgestellt, gestartet wird am Gerät. Pause und Fortsetzen bietet die Bibliothek für dieses Modell nicht an.

```yaml
action: vesync.stage_cook_program
target:
  entity_id: button.airfryer_garprogramm_ubertragen
data:
  mode: fries
  temperature: 200
  duration: 12
```

## Installation (HACS)

1. HACS → ⋮ → Benutzerdefinierte Repositories → `https://github.com/slu125/ha-vesync-cosori-lite`, Typ „Integration“
2. „VeSync (mit Cosori Lite CAF-LI401S)“ herunterladen, Home Assistant neu starten
3. Ein bestehender VeSync-Eintrag wird übernommen, die Zugangsdaten müssen nicht neu eingegeben werden.

Abfrage alle 60 s. Solange eine Fritteuse heizt oder gart und 3 Minuten nach „Garprogramm übertragen“ alle 10 s.

Beim Start installiert HA pyvesync aus dem GitHub-Release; GitHub muss dafür erreichbar sein.

## Zurück zur eingebauten Integration

In HACS entfernen und neu starten. HA installiert dann wieder das pyvesync der eingebauten Integration. Entitäten, die es dort nicht gibt, erscheinen als „nicht mehr bereitgestellt“ und können gelöscht werden. Sobald ein Home-Assistant-Release den CAF-LI401S unterstützt, wird dieses Repository archiviert.
