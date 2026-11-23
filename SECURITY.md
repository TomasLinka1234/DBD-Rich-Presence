# Bezpečnost

## Co program dělá a co ne

| | |
|---|---|
| Čte obrazovku | ano, jen okno Dead by Daylight, a jen když hra běží. Text čte OCR **přímo v počítači** |
| Ukládá screenshoty | ne (jen když si sám zapneš ukládání nebo ladění v nastavení, a to jen k tobě do `%APPDATA%\DbD Rich Presence`) |
| Statistiky zápasů | jen u tebe v `zapasy.jsonl` (postava, mapa, délka, výsledek); nikam se neposílají, do Discordu jde jen krátký souhrn ve statusu (jde vypnout) |
| Čte paměť hry, mění herní soubory, vkládá se do hry | **ne** |
| Práva správce | ne, běží pod tvým účtem |
| Zápis do systému | jen hodnota `DbD Rich Presence` v `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (spouštění se zapnutím Windows, jde vypnout v menu) |
| Telemetrie, reklamy, sběr dat | **ne** |

## Kam se program připojuje

| Kam | Proč |
|---|---|
| Discord na tvém počítači (místní roura `discord-ipc`) | nastavení statusu |
| `discord.com/api/.../applications/<id>/assets` | seznam obrázků nahraných v Discord aplikaci (veřejný, bez přihlášení) |
| `deadbydaylight.wiki.gg` | nejvýš 1× denně seznam nových postav/map, odkazy na portréty |

Program sám nic jiného nestahuje. Odkazy na obrázky (portréty z wiki, případně `placehold.co`
s číslem prestige, když chybí odznak) jen předá Discordu jako součást statusu a ten si je načte.

Nic jiného se nikam neposílá. Žádný přihlašovací token, žádné screenshoty.
Všechno je vidět ve zdrojovém kódu (`app/images.py`, `app/wiki_data.py`, `app/presence.py`).

## Jak ověřit, že .exe je z tohohle kódu

Každý `.exe` ve [Vydáních](https://github.com/TomasLinka1234/DBD-Rich-Presence/releases)
sestavil GitHub Actions z veřejného kódu (`.github/workflows/build.yml`), nikdo ho neposílal ručně.
GitHub k němu vydává podepsané potvrzení původu (build provenance attestation):

```
gh attestation verify DbD-Rich-Presence.exe --repo TomasLinka1234/DBD-Rich-Presence
```

nebo porovnej otisk souboru s tím v popisu vydání:

```
Get-FileHash .\DbD-Rich-Presence.exe -Algorithm SHA256
```

Kdo chce, sestaví si `.exe` sám (návod v [README](README.md)).

## Antiviry

Program je zabalený nástrojem PyInstaller (Python + knihovny v jednom souboru) a není podepsaný
placeným certifikátem. Windows SmartScreen proto u nových verzí ukáže varování a některé méně
známé antiviry občas hlásí PyInstaller programy jako podezřelé, i když v nich nic škodlivého není
(tzv. false positive). Pokud ti antivirus něco hlásí, napiš název antiviru a hlášení do Issues.

## Nahlášení problému

Bezpečnostní chybu prosím nahlas přes
[Security → Report a vulnerability](https://github.com/TomasLinka1234/DBD-Rich-Presence/security/advisories/new),
ne veřejně v Issues.
