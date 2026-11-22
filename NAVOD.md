# DbD Rich Presence

Ukazuje v Discordu živě, **koho hraješ**, **na jaké mapě** a **jak dlouho zápas běží**:

```
Dead by Daylight
Killer: The Judgment
Rotten Fields (Coldwind Farm)
12:34 uplynulo
```

Program každou chvíli vyfotí obrazovku a přečte z ní text: jméno postavy v menu, tlačítko
PLAY/READY, název mapy na začátku zápasu a obrazovku po zápase. Všechno se čte přímo
v počítači (OCR), na internet nic neposílá. Výjimkou je jen tvůj status v Discordu.

---

## Jednorázové nastavení (asi 5 minut)

### 1. Vytvoř si „aplikaci“ v Discordu (kvůli názvu v profilu)

1. Otevři <https://discord.com/developers/applications> a přihlas se.
2. Klikni na **New Application**, zadej jméno **Dead by Daylight** a potvrď.
   V profilu pak bude „Hraje **Dead by Daylight**“.
3. Na stránce **General Information** zkopíruj **Application ID** (dlouhé číslo).
4. Otevři soubor `nastaveni.json` (pravým tlačítkem → Otevřít v programu → Poznámkový blok)
   a místo `SEM_VLOZ_APPLICATION_ID` vlož to číslo. Uvozovky nech, pak soubor ulož:
   ```
   "discord_application_id": "1234567890123456789",
   ```
5. *(Volitelné)* Obrázky v profilu (mapa + ikonka killer/survivor): viz sekci
   [Obrázky v profilu](#obrázky-v-profilu) níže.

### 2. Discord

- Musí běžet **aplikace Discord** v počítači. Discord v prohlížeči nestačí.
- V Discordu: **Nastavení → Soukromí aktivity → Sdílet svou aktivitu** musí být zapnuté.

### 3. Hra

- **Options → Graphics → Display Mode: Windowed Fullscreen** (okno přes celou obrazovku).
  V klasickém fullscreenu může Windows místo hry vyfotit černou obrazovku.
- Hra musí být **v angličtině**.

### 4. Spuštění

- Dvakrát klikni na **`spustit.bat`**.
- Napoprvé se nainstaluje Python a potřebné knihovny. Stahuje se asi 150 MB a trvá to
  2 až 5 minut, ale jen jednou.
- Když Windows ukáže „Systém Windows ochránil počítač“, klikni na **Další informace → Přesto spustit**.
- Okno nech otevřené, klidně minimalizované. Je jedno, jestli spustíš dřív hru, nebo program.
- Program ukončíš zavřením okna. Status z Discordu sám zmizí.

### 5. Automatické spouštění (doporučeno)

Aby se nemuselo pokaždé pouštět `spustit.bat`:

- Dvakrát klikni na **`zapnout_autostart.bat`**.
- Program pak poběží **na pozadí bez okna**, s ikonkou vpravo dole u hodin (na Windows 11
  případně pod šipkou nahoru). Po zapnutí počítače se spustí sám a čeká, až zapneš
  Dead by Daylight. Bez hry skoro nic nežere: OCR se načte až se hrou a po jejím zavření
  se zase uvolní.
- **Pravým tlačítkem na ikonku** uvidíš, co program právě ukazuje v Discordu, a můžeš otevřít
  log, složku programu, vypnout spouštění s Windows nebo program ukončit.
- Barva tečky na ikonce: **šedá** = čeká na hru, **zelená** = ukazuje se v Discordu,
  **oranžová** = hra běží, ale Discord ne, **červená** = chyba (podrobnosti v `log.txt`).
- Vypnout: **`vypnout_autostart.bat`** (nebo v menu ikonky odškrtni „Spouštět se zapnutím Windows“).
- Když chceš vidět výpis v okně (třeba kvůli hledání chyby), ukonči program na pozadí
  a pusť `spustit.bat`. Obě verze najednou běžet nemůžou.

---

## Co se kdy v Discordu ukazuje

| Ve hře | V Discordu |
|---|---|
| menu | postava · „V menu“ |
| lobby | postava · „V lobby“ nebo „Čeká na zápas“ |
| načítání | postava · „Načítá se zápas“ |
| **zápas** | **postava · mapa · čas od začátku zápasu** |
| po zápase | postava · „Po zápase“ |

**Jak program pozná postavu:**
- **Killer:** ze jména pod tlačítkem READY/CANCEL nebo ze záložky postav (Characters) v lobby.
- **Survivor:** ze jména nad tvou postavou v lobby (podle tvého jména `jmeno_ve_hre`)
  nebo ze záložky postav.
- Po zápase si to ještě ověří ve scoreboardu.
- Pamatuje si posledního killera i survivora, i po vypnutí programu.

> **Tip:** Kdyby postava neseděla, otevři v lobby na chvilku záložku postav (Characters).
> Program si jméno přečte vlevo nahoře.

**Mapa** se čte z názvu, který se na pár sekund ukáže vlevo dole hned na začátku zápasu.
Když se ji přečíst nepodaří, ukáže se jen „V zápase“.

**Prestige** se čte z odznaku vlevo od jména v menu postav (Characters) a po zápase
ze scoreboardu. V lobby se pak ukáže text „V lobby · Prestige 6“ a v rohu obrázku
**odznak prestige** (v zápase je tam místo něj ikona mapy).
Program si prestige pamatuje pro každou postavu zvlášť.

### Odznaky prestige (jednou nahrát)

Ve složce `odznaky` je hotových **100 odznaků** (`odznak_1.png` … `odznak_100.png`)
ve stylu hry: 1–25 kulaté, 26–50 kosočtverec, 51–75 šestiúhelník, 76–99 osmiúhelník
a 100 rudý krystal. Barva se mění po pěti úrovních (šedá, bronzová, modrošedá, zlatá,
červená) a ozdoby kolem odznaku přibývají stejně jako ve hře.

1. Otevři <https://discord.com/developers/applications> → tvoje aplikace → **Rich Presence → Art Assets**.
2. Klikni na **Přidat obrázky** (Add Image(s)), ve složce `odznaky` označ všechny obrázky (Ctrl+A) a potvrď.
3. Jména nech, jak jsou (`odznak_1`, `odznak_2`…), a dole klikni na **Uložit změny** (Save Changes).

Program si nahrané odznaky najde sám do pár minut (Discordu někdy chvilku trvá,
než nové obrázky začne ukazovat). Dokud nahrané nejsou, ukazuje se jednoduchý odznak
s číslem. Odznak záleží jen na úrovni, takže stejná prestige = stejný odznak u všech postav.

> Starší sada `prestige_1` … `prestige_100` (menší odznaky) se dál použije, dokud nenahraješ novou.
> Pak ji v Art Assets můžeš smazat, ale nemusíš: místa je 300.

**Skiny:** Legendary skiny, které mění postavu (např. **Rize Kamishiro** pro The Ghoul nebo
**Claire Redfield** pro Jill Valentine), program pozná a ukáže takhle:

```
Killer: Rize Kamishiro (The Ghoul)
```

Když hra ukáže jméno, které program nezná (nový skin nebo nová postava), vezme ho tak,
jak je napsané v menu postav, a roli pozná podle záložky ALL KILLERS / ALL SURVIVORS.
Obyčejné oblečky jméno postavy nemění, takže se nezobrazují.

---

## Obrázky v profilu

Funguje to podobně jako u Fortnite: **velký obrázek = portrét tvé postavy** (u skinu portrét skinu,
třeba Rize Kamishiro) a **malá kulatá ikonka v rohu = v zápase ikona mapy, v lobby odznak
s prestige**. Malá ikonka je vždycky v pravém dolním rohu velkého obrázku, to rozložení
určuje Discord.

**Nic nahrávat nemusíš.** Portréty a ikony map si program sám najde na
[Dead by Daylight Wiki](https://deadbydaylight.wiki.gg) a adresy si uloží
(`app/obrazky_cache.json`). Discord pak obrázek zobrazí přímo z wiki.
Když chceš velký obrázek mapy a malou ikonku role, nastav `"velky_obrazek": "mapa"`.

*(Volitelné)* **Vlastní obrázky** mají přednost před wiki. Nahrávají se do tvé aplikace na
<https://discord.com/developers/applications> → tvoje aplikace → **Rich Presence → Art Assets**
pod jménem podle pravidla: malá písmena, mezery nahradí `_` a apostrofy se vynechají.
- `killer`, `survivor`: ikonky rolí (hotové jsou ve složce `ikony`)
- `rotten_fields`, `tricksters_delusion`…: mapy, `coldwind_farm`…: realmy
- `the_ghoul`, `rize_kamishiro`, `meg_thomas`…: postavy a skiny
- `odznak_1` … `odznak_100`: odznaky prestige (hotové ve složce `odznaky`, viz výš)
- `logo`: výchozí obrázek

Nově nahrané obrázky začne program používat do pár minut.

---

## Nastavení (`nastaveni.json`)

| Položka | Co dělá |
|---|---|
| `discord_application_id` | ID tvé aplikace z kroku 1 (povinné) |
| `jazyk` | `cs` = česky, `en` = anglicky (texty v Discordu) |
| `ukazat_mapu` | `true` / `false`: ukazovat mapu |
| `ukazat_cas_zapasu` | `true` / `false`: ukazovat čas |
| `jmeno_ve_hre` | tvoje jméno ve hře (podle něj se pozná tvůj survivor v lobby) |
| `ukazat_zakladni_postavu` | `true` = u skinu ukázat i základní postavu: „Rize Kamishiro (The Ghoul)“ |
| `ukazat_prestige` | `true` = v lobby ukázat prestige postavy |
| `prestige_ikona` | `true` = v lobby dát do rohu obrázku odznak s číslem prestige |
| `ukladat_odznaky_prestige` | `true` = vyříznout odznak prestige ze hry do `obrazky_k_nahrani` (jen když chybí složka `odznaky`) |
| `velky_obrazek` | `postava` = velký portrét postavy + malá ikona mapy; `mapa` = naopak |
| `obrazky_z_wiki` | `true` = portréty a ikony map brát z DbD wiki |
| `ukladat_obrazky_map` | `true` = ukládat snímek každé nové mapy do `obrazky_k_nahrani` (pro vlastní obrázky) |
| `obrazek`, `obrazek_killer`, `obrazek_survivor` | jiný obrázek místo `logo` / `killer` / `survivor`: jméno z Art Assets nebo odkaz `https://…` (nepovinné) |
| `snimani` | `auto` / `mss` / `dxcam`: způsob focení obrazovky (nech `auto`) |
| `vlakna_ocr` | kolik jader procesoru smí OCR použít (2; při sekání hry dej 1) |
| `debug` | `true` = podrobný výpis a ukládání snímků do složky `debug` |

| `novinky_z_wiki` | `true` = jednou denně se podívat na DbD wiki po nových postavách, mapách a skinech |

**Nové postavy, mapy a skiny** si program sám stahuje z DbD wiki (jednou denně, a jen když
se tam něco změnilo). Nové věci jen přidá, nic nemaže, a do logu napíše, co přibylo
(„Novinky z DbD wiki: killer …“). Stažený seznam je v `app/dbd_data_wiki.json`. Když chceš
něco opravit ručně, pořád to jde připsat do `app/dbd_data.json`.

---

## Když něco nejde

- **Program čte jen to, co je na obrazovce vidět.** Když je přes hru jiné okno (prohlížeč,
  Discord nebo okno tohohle programu), čtení počká a v okně se objeví „Hra je schovaná za
  jiným oknem“. Okno programu klidně minimalizuj.
- **Prestige se neukazuje:** otevři v lobby na pár sekund záložku postav (Characters).
- **Nic se nečte:** v lobby spusť **`diagnostika.bat`**, do 8 sekund se přepni do hry
  a pak mi pošli výpis (a případně snímky ze složky `debug`).

- **V Discordu se nic neukazuje:** zkontroluj krok 2 (aplikace Discord běží, sdílení aktivity
  je zapnuté) a Application ID v `nastaveni.json`. V okně programu je vidět, co se děje.
- **„Snímek obrazovky je pořád černý“:** přepni hru na *Windowed Fullscreen* (krok 3).
- **Špatně pozná postavu nebo mapu:** udělej ve hře screenshot (F12 ve Steamu nebo PrtScn)
  a přetáhni ho myší na **`test_screenshotu.bat`**. Vypíše, co na obrázku přečetl.
  Výpis spolu se souborem `log.txt` mi pošli.
- **Hra se seká:** nastav `"vlakna_ocr": 1`.
- **DbD je v profilu dvakrát** (jednou ho ukazuje sám Discord, jednou tenhle program): dej vědět.

## Je to bezpečné?

Program nečte paměť hry, nemění herní soubory a nic do hry nevkládá. Jen fotí obrazovku,
stejně jako OBS nebo Discord při streamování, a text z ní čte u tebe v počítači.
Na stejném principu (čtení obrazovky) fungují i jiné komunitní nástroje pro DbD,
třeba overlaye s mapami.
