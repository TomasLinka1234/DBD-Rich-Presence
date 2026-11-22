# DbD Rich Presence

<img src="app/ikona.png" width="96" align="right" alt="logo">

Discord status pro **Dead by Daylight**: živě ukazuje, **koho hraješ**, **na jaké mapě**,
**jak dlouho zápas běží** a v lobby i **prestige** tvé postavy.

```
Dead by Daylight
Killer: The Krasue
Rotten Fields (Coldwind Farm)
12:34 uplynulo
```

## Stažení

**[⬇ DbD-Rich-Presence.exe](https://github.com/TomasLinka1234/DBD-Rich-Presence/releases/latest/download/DbD-Rich-Presence.exe)**
(jeden soubor, nic se neinstaluje)

1. Stáhni `DbD-Rich-Presence.exe` a dej ho, kam chceš (třeba do Dokumentů).
2. Spusť ho. Když Windows ukáže *„Systém Windows ochránil počítač“*, klikni na
   **Další informace → Přesto spustit** (program není podepsaný certifikátem).
3. Na otázku, jestli se má spouštět se zapnutím Windows, dej **Ano**.

Hotovo. Program běží na pozadí s ikonkou vpravo dole u hodin a sám počká, až zapneš hru.
Ve hře nastav **Windowed Fullscreen** a angličtinu, v Discordu musí být zapnuté
**Sdílet svou aktivitu**. Podrobnosti jsou v **[NAVOD.md](NAVOD.md)**.

## Co umí

- postava včetně legendárních skinů (Rize Kamishiro = The Ghoul), mapa a čas zápasu
- velký portrét postavy a malá ikona mapy, v lobby místo ní odznak prestige
- běh na pozadí bez okna, spouštění se zapnutím Windows, nastavení z menu ikonky
- nové postavy, mapy a skiny si sám jednou denně doplní z [DbD wiki](https://deadbydaylight.wiki.gg)

Program čte obrazovku (OCR přímo v počítači). Do hry nijak nezasahuje: nečte její paměť ani
nemění soubory, jen fotí obrazovku jako OBS nebo Discord při streamování.

## Pro vývojáře

```
pip install -r requirements.txt
python app/main.py                 # na pozadí s ikonkou
python app/main.py --konzole       # v okně s výpisem
python app/main.py --test obr.png  # co program přečte ze screenshotu
```

`.exe` se sestavuje automaticky na GitHubu (`.github/workflows/build.yml`, PyInstaller)
při každé změně a nová verze (`app/version.py`) se objeví ve [Vydáních](../../releases).
Složka `assets/` obsahuje obrázky k nahrání do Art Assets vlastní Discord aplikace
(odznaky prestige 1–100, ikonky rolí) a zdroj loga.

Dead by Daylight je ochranná známka Behaviour Interactive. Tohle je neoficiální fanouškovský
nástroj; portréty a ikony map se načítají z komunitní DbD wiki.
