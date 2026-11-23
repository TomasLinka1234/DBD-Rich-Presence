# Návod: DbD Rich Presence

## Spuštění

1. Stáhni **[DbD-Rich-Presence.exe](https://github.com/TomasLinka1234/DBD-Rich-Presence/releases/latest/download/DbD-Rich-Presence.exe)**
   a dej ho, kam chceš (třeba do Dokumentů). Nic se neinstaluje, je to jeden soubor.
2. Spusť ho. Když Windows ukáže *„Systém Windows ochránil počítač“*, klikni na
   **Další informace → Přesto spustit**.
3. Napoprvé se zeptá, jestli se má **spouštět se zapnutím Windows**. Dej **Ano**.

Program pak běží **na pozadí bez okna**, s ikonkou vpravo dole u hodin (na Windows 11
případně pod šipkou nahoru). Sám počká, až zapneš Dead by Daylight. Bez hry skoro nic
nežere: čtení obrazovky se načte až se hrou a po jejím zavření se zase uvolní.
Start po zapnutí počítače trvá pár sekund, než se program rozbalí.

### Co musí být nastavené

- **Discord**: musí běžet aplikace Discord v počítači (prohlížeč nestačí) a v
  **Nastavení → Soukromí aktivity** musí být zapnuté **Sdílet svou aktivitu**.
- **Hra**: **Options → Graphics → Display Mode: Windowed Fullscreen** a hra v **angličtině**.
  V klasickém fullscreenu může Windows místo hry vyfotit černou obrazovku.

## Ikonka u hodin

Barva tečky: **šedá** = čeká na hru, **zelená** = ukazuje se v Discordu,
**oranžová** = hra běží, ale Discord ne, **červená** = chyba (podrobnosti v logu).

Pravým tlačítkem na ikonku:

- nahoře je vidět, co program právě ukazuje v Discordu
- **Statistiky**: otevře v prohlížeči přehled odehraných zápasů (viz níž)
- **Nastavení**: otevře soubor s nastavením v Poznámkovém bloku; po uložení se samo načte
- **Otevřít log**, **Otevřít složku s daty**
- **Spouštět se zapnutím Windows** (zapnout / vypnout)
- **Ukončit**

## Co se kdy v Discordu ukazuje

| Ve hře | V Discordu |
|---|---|
| menu | postava · „V menu“ |
| lobby | postava · „V lobby“ / „Čeká na zápas“ · prestige |
| načítání | postava · „Načítá se zápas“ |
| **zápas** | **postava · mapa · čas od začátku zápasu** |
| po zápase | postava · „Po zápase · Útěk“ / „Po zápase · 4 zabití“ |

V menu a v lobby se status každých 20 sekund vystřídá s dnešními statistikami, třeba
„Dnes 4 zápasy · 3 výhry“ (počítá se role, kterou zrovna hraješ). Po najetí myší na portrét
je vidět i souhrn za postavu: „The Krasue · Prestige 6 · 23 zápasů · 14 výher“.

Velký obrázek je portrét postavy, malý v rohu je v zápase ikona mapy a v lobby
odznak prestige. **Prestige** se čte z odznaku vedle jména v menu postav (Characters)
a ze scoreboardu po zápase; když se neukazuje, otevři v lobby na pár sekund záložku postav.

## Statistiky

Program si sám počítá každý odehraný zápas: postavu, mapu, délku a výsledek. Výsledek čte
z obrazovky konce zápasu: u survivora **útěk / obětování / smrt**, u killera počet zabití podle
nápisu (**Merciless Killer** = 4, **Ruthless** = 3, **Brutal** = 2, **The Entity Hungers…** = 0–1).
**Výhra** = útěk, nebo aspoň 3 zabití za killera. Když se obrazovka konce nepřečte (odpojení,
hra zavřená uprostřed zápasu), zápas se započítá s výsledkem „nezjištěno“ a do výher se nepočítá.

Ikonka → **Statistiky** otevře přehled: dnes / tento týden / celkem, tabulky podle postav
(útěky, 4K/3K/2K…, odehraný čas), mapy a posledních 30 zápasů. „Dnes“ začíná ve 4:00 ráno,
takže noční hraní po půlnoci se počítá ještě ke včerejšku.

Zápasy jsou jen u tebe v souboru `%APPDATA%\DbD Rich Presence\zapasy.jsonl` (jeden řádek
= jeden zápas). Statistiky smažeš smazáním toho souboru.

## Nastavení

Ikonka → **Nastavení** (soubor `%APPDATA%\DbD Rich Presence\nastaveni.json`):

| Položka | Co dělá |
|---|---|
| `discord_application_id` | Discord aplikace, pod kterou se status ukazuje (výchozí je hotová aplikace „Dead by Daylight“ i s odznaky) |
| `jazyk` | `cs` = česky, `en` = anglicky |
| `ukazat_mapu`, `ukazat_cas_zapasu` | `true` / `false` |
| `jmeno_ve_hre` | tvoje jméno ve hře (program si ho jinak zjistí sám) |
| `ukazat_zakladni_postavu` | `true` = u skinu ukázat i základní postavu: „Rize Kamishiro (The Ghoul)“ |
| `ukazat_prestige`, `prestige_ikona` | prestige v textu / odznak v rohu obrázku |
| `statistiky` | `true` = počítat odehrané zápasy (soubor `zapasy.jsonl`) |
| `ukazat_statistiky` | `true` = ukazovat v Discordu dnešní zápasy, výsledek po zápase a souhrn za postavu |
| `velky_obrazek` | `postava` = velký portrét + malá mapa; `mapa` = naopak |
| `obrazky_z_wiki` | portréty a ikony map z DbD wiki |
| `novinky_z_wiki` | jednou denně doplnit nové postavy, mapy a skiny z DbD wiki |
| `snimani` | `auto` / `mss` / `dxcam`: způsob focení obrazovky (nech `auto`) |
| `vlakna_ocr` | kolik jader procesoru smí čtení textu použít (2; když se hra seká, dej 1) |
| `debug` | `true` = podrobný log a ukládání snímků do složky `debug` |

Uvozovky a čárky musí zůstat, jak jsou. Když soubor smažeš, vytvoří se znovu s výchozími hodnotami.

## Vlastní Discord aplikace (nepovinné)

Výchozí aplikace „Dead by Daylight“ už má nahrané odznaky prestige, takže není potřeba nic
zakládat. Kdybys chtěl vlastní: na <https://discord.com/developers/applications> vytvoř aplikaci,
její **Application ID** dej do nastavení a do **Rich Presence → Art Assets** nahraj obrázky ze
složky [`assets/odznaky`](assets/odznaky) (Discord bere zhruba 10 obrázků najednou, nahrávej
po menších dávkách).

## Když něco nejde

- **Nic se neukazuje:** zkontroluj Discord (aplikace běží, sdílení aktivity zapnuté) a barvu
  tečky na ikonce. V logu (ikonka → Otevřít log) je vidět, co program dělá.
- **Hra je schovaná:** program čte jen to, co je na obrazovce vidět. Když je přes hru jiné okno,
  čtení počká.
- **Černá obrazovka / nic se nečte:** přepni hru na *Windowed Fullscreen*.
- **Hra se seká:** v nastavení dej `"vlakna_ocr": 1`.
- **Špatně pozná postavu nebo mapu:** pošli screenshot ze hry a log.

Všechna data programu (nastavení, log, stav, statistiky) jsou v `%APPDATA%\DbD Rich Presence`.
**Odinstalace:** ikonka → odškrtni *Spouštět se zapnutím Windows* → *Ukončit*, pak smaž
`DbD-Rich-Presence.exe` a tu složku s daty.

## Je to bezpečné?

Program nečte paměť hry, nemění herní soubory a nic do hry nevkládá. Jen fotí obrazovku,
stejně jako OBS nebo Discord při streamování, a text z ní čte u tebe v počítači.
Na internet posílá jen tvůj status do Discordu a jednou denně se podívá na DbD wiki.
Celý kód je veřejný a `.exe` sestavuje GitHub automaticky; jak si to ověřit a kam přesně se
program připojuje, je v [SECURITY.md](SECURITY.md).
