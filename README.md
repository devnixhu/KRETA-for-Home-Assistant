# KRÉTA for Home Assistant

<p align="center">
  <strong>KRÉTA-adatok a Home Assistantban, egyszerűen és automatizálhatóan.</strong>
</p>

<p align="center">
  <a href="https://www.home-assistant.io/">
    <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5?logo=homeassistant&logoColor=white">
  </a>
  <a href="https://hacs.xyz/">
    <img alt="HACS" src="https://img.shields.io/badge/HACS-Custom%20Repository-41BDF5">
  </a>
  <a href="./LICENSE">
    <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg">
  </a>
  <img alt="KRÉTA Unofficial" src="https://img.shields.io/badge/KR%C3%89TA-Unofficial-orange">
</p>

<p align="center">
  <a href="#mi-ez">Mi ez?</a> •
  <a href="#főbb-funkciók">Funkciók</a> •
  <a href="#telepítés">Telepítés</a> •
  <a href="#beállítás">Beállítás</a> •
  <a href="#biztonság-és-adatvédelem">Biztonság</a> •
  <a href="#licenc-és-eredeti-projekt">Licenc</a>
</p>

---

> [!IMPORTANT]
> **Ez egy NEM hivatalos, közösségi Home Assistant-integráció.**
>
> A projekt NEM áll kapcsolatban a KRÉTA rendszer fejlesztőjével vagy üzemeltetőjével, továbbá NEM hivatalos Home Assistant- vagy HACS-projekt.
>
> A KRÉTA hivatalos tájékoztatása szerint a tanulói alkalmazások által használt API-k nem nyilvánosak, és használatukat a hivatalos KRÉTA-alkalmazások számára tartják fenn. Emiatt az integráció működése bármikor megváltozhat vagy megszűnhet.
>
> A projekt használata saját felelősségre történik.

---

## Mi ez?

A **KRÉTA for Home Assistant** egy közösségi custom integration, amely a KRÉTA rendszerből elérhető egyes tanulói információkat teszi használhatóvá a Home Assistantban.

A cél, hogy a napi iskolai információk egy helyen, automatizálható formában jelenjenek meg:

- Home Assistant-dashboardokon
- naptárnézetben
- automatizálásokban
- mobilértesítésekben
- WallPanelen
- más otthoni információs kijelzőkön

A projekt a [`majorcs/kreta-homeassistant`](https://github.com/majorcs/kreta-homeassistant) nyílt forráskódú projektjén alapul, és annak továbbfejlesztett változata.

---

## Főbb funkciók

A jelenlegi verzió az upstream projekt funkcióira épül.

### Órarend és naptár

- **Órarend** megjelenítése Home Assistant-naptárként
- **Bejelentett számonkérések** megjelenítése az órarend mellett vagy külön naptári eseményként
- gépileg feldolgozható **JSON-szenzor** órarendi és számonkérési adatokhoz
- **bináris szenzorok** a mai és holnapi tanítási, illetve számonkérési naphoz
- tanév rendjének kezelése

### Jegyek és tanulmányi adatok

- **érdemjegyek kezelése**
- érdemjegyekhez kapcsolódó JSON-adatok
- új értékelések követésének lehetősége
- tanulói profiladatok megjelenítése, ha azokat a KRÉTA visszaadja

### Házi feladatok

- **házi feladatok kezelése**
- közelgő házi feladatok követése
- gépileg feldolgozható adatok automatizálásokhoz

### Diagnosztika és frissítés

- **Utolsó frissítés** diagnosztikai szenzor
- **Frissítési állapot** szenzor az adatlekérés állapotával
- **kézi azonnali frissítés**
- **automatikus időzített frissítés**
- konfigurálható frissítési időköz

### Több fiók

- **több tanuló / KRÉTA-fiók** kezelése
- minden tanuló külön integrációs példányként használható

> [!NOTE]
> Egyes részletes vagy JSON-alapú entitások alapértelmezésben kikapcsolva lehetnek.
>
> Az elérhető funkciók a KRÉTA rendszer és az integráció verziójának változásával eltérhetnek.

---

## Telepítés

### HACS használatával

1. Nyisd meg a **HACS** felületet a Home Assistantban.
2. Menj az **Integrations** részhez.
3. Nyisd meg az egyedi repositoryk hozzáadására szolgáló menüpontot.
4. Add hozzá ezt a repositoryt:

```text
https://github.com/devnixhu/KRETA-for-Home-Assistant
```

5. Típusnak válaszd az **Integration** lehetőséget.
6. Telepítsd a **KRÉTA for Home Assistant** integrációt.
7. Indítsd újra a Home Assistantot, ha erre a rendszer figyelmeztet.

---

### Kézi telepítés

1. Töltsd le a repository legfrissebb verzióját.
2. Másold a:

```text
custom_components/kreta
```

mappát a Home Assistant konfigurációs könyvtárának:

```text
custom_components
```

mappájába.

A végeredmény például így nézzen ki:

```text
/config/
└── custom_components/
    └── kreta/
        ├── __init__.py
        ├── manifest.json
        ├── config_flow.py
        └── ...
```

3. Indítsd újra a Home Assistantot.
4. Add hozzá az integrációt a Home Assistant felületén.

---

## Beállítás

1. Nyisd meg a:

   **Beállítások → Eszközök és szolgáltatások**

   oldalt.

2. Válaszd az **Integráció hozzáadása** lehetőséget.

3. Keresd meg a **KRÉTA** integrációt.

4. Add meg az intézményi azonosítót és a frissítési beállításokat.
5. Nyisd meg a megjelenő hivatalos KRÉTA bejelentkezési hivatkozást.
6. A KRÉTA oldalán végezd el a jelszavas és szükség esetén a kétlépcsős azonosítást.
7. Másold vissza a Home Assistantba a böngészőben megnyitott teljes végső visszatérési URL-t.

A Home Assistant nem kapja meg a KRÉTA-felhasználónevet, a jelszót vagy a kétlépcsős azonosítási kódot. A visszatérési URL egyszer használható OAuth-kódját PKCE védi, és az integráció ellenőrzi a hostot, az útvonalat és a bejelentkezési kísérlethez tartozó `state` értéket.

Több KRÉTA-fiók külön integrációs példányként adható hozzá.

---

## Használat

Az integráció telepítése után az elérhető adatok Home Assistant-entitásokként és naptári eseményekként jelennek meg.

### Tipikus felhasználás

- aktuális tanóra megjelenítése
- következő tanóra megjelenítése
- napi órarend megjelenítése
- számonkérések követése
- iskolai események követése
- érdemjegyek feldolgozása
- házi feladatok követése
- dashboardok készítése
- Home Assistant-automatizálások indítása
- mobilértesítések létrehozása
- WallPanel-értesítések létrehozása

---

## WallPanel és értesítések

A KRÉTA-integrációt érdemes **adatforrásként** használni, az értesítéseket pedig a Home Assistanton keresztül kezelni.

### Javasolt felépítés

```text
KRÉTA
  │
  ▼
KRÉTA for Home Assistant
  │
  ▼
Home Assistant
  │
  ├── Dashboard
  ├── Automation
  ├── Mobile notification
  └── WallPanel
```

Így a WallPanelnek nincs szüksége:

- közvetlen KRÉTA-hozzáférésre
- KRÉTA-felhasználónévre
- KRÉTA-jelszóra
- KRÉTA-tokenekre

A WallPanel csak a Home Assistant által már feldolgozott információkat jeleníti meg.

---

## Példa automatizálási lehetőségek

A Home Assistant segítségével például ilyen automatizálások készíthetők:

### Új jegy

```text
Új KRÉTA-értékelés
        │
        ▼
Home Assistant
        │
        ├── telefonos értesítés
        ├── WallPanel popup
        └── dashboard frissítés
```

### Következő óra

Például egy dashboardon:

```text
Következő óra

INFORMATIKA
09:55 – 10:40
214-es terem
```

### Reggeli összefoglaló

Például:

```text
Mai nap

6 tanóra
Első óra: Matematika
Utolsó óra: Angol

1 számonkérés
2 házi feladat
```

> [!NOTE]
> Az itt bemutatott automatizálási példák nem feltétlenül érhetők el alapértelmezésben a jelenlegi verzióban.

---

## Biztonság és adatvédelem

A KRÉTA-fiók tanulmányi és személyes adatokat tartalmaz, ezért a hitelesítési adatokat különösen érzékeny információként kell kezelni.

### Ajánlott

- csak saját vagy jogszerűen kezelt KRÉTA-fiókot használj
- soha ne tölts fel valódi jelszót GitHubra
- soha ne tölts fel access vagy refresh tokent GitHubra
- ne tölts fel Home Assistant `.storage` fájlokat
- ne oszd meg a `.storage` könyvtár tartalmát
- ne tegyél valódi KRÉTA API-válaszokat publikus issue-ba
- ne tegyél személyes adatokat logpéldákba
- publikus hibajegyek előtt anonimizáld a logokat
- tartsd naprakészen a Home Assistantot
- tartsd naprakészen az integrációt

> [!WARNING]
> A custom integration a Home Assistant folyamatán belül fut.
>
> Csak olyan verziót telepíts, amelynek a forráskódjában megbízol.

---

## Adatkezelési alapelvek

A projekt célja, hogy a lehető legkevesebb érzékeny adatot kezelje és tárolja.

A tervezett alapelvek:

- minimális adattárolás
- csak szükséges adatok lekérése
- lehetőség szerint csak read-only hozzáférés
- kizárólag a futáshoz szükséges refresh token tartós tárolása
- érzékeny adatok kizárása a logokból
- érzékeny adatok kizárása a diagnosztikából
- nyers KRÉTA-válaszok tárolásának kerülése
- harmadik félnek történő adattovábbítás kerülése

---

## Projektirány

A fork fejlesztési célja egy egyszerűbben auditálható, **privacy- és security-first** KRÉTA-integráció kialakítása.

### Tervezett fejlesztési irányok

- minimális adattárolás
- hitelesítési adatok biztonságosabb kezelése
- érzékeny adatok kizárása a logokból
- érzékeny adatok kizárása a diagnosztikából
- kizárólag szükséges KRÉTA-végpontok használata
- jobb hálózati request-kezelés
- biztonságosabb tokenkezelés
- natív Home Assistant-eventek
- új jegy esemény
- új üzenet esemény
- új házi feladat esemény
- órarendváltozás esemény
- aktuális tanóra szenzor
- következő tanóra szenzor
- mai órák összefoglalója
- holnapi órák összefoglalója
- WallPanel-barát automatizálási példák
- jobb diagnosztika
- jobb hibakezelés
- részletes security dokumentáció
- részletes privacy dokumentáció
- automatizált security tesztek

> [!NOTE]
> A felsorolt tervezett funkciók nem feltétlenül érhetők el a jelenlegi kiadásban.

---

## Tervezett architektúra

A projekt fejlesztési iránya szerint a KRÉTA-hozzáférést érdemes különválasztani a Home Assistant többi funkciójától.

```text
                    KRÉTA
                      │
                      │ HTTPS
                      ▼
              KRÉTA API kliens
                      │
                      ▼
             Home Assistant
             Data Coordinator
                      │
          ┌───────────┼───────────┐
          │           │           │
          ▼           ▼           ▼
       Sensors      Calendar     Events
          │           │           │
          └───────────┼───────────┘
                      │
                      ▼
              Home Assistant
               Automations
                      │
          ┌───────────┼───────────┐
          │           │           │
          ▼           ▼           ▼
       WallPanel    Mobile      Dashboard
```

Így maga a KRÉTA-integráció nem szükséges, hogy közvetlenül kommunikáljon WallPanellel vagy más külső megjelenítővel.

---

## Fejlesztés és tesztelés

A projekt módosítása után futtasd a teszteket, mielőtt kiadást készítesz.

### Függőségek telepítése

```bash
python -m pip install -r requirements-dev.txt -r requirements-ha.txt
```

### Tesztek futtatása

```bash
pytest
```

### Ajánlott ellenőrzések

A repository CI-je számára ajánlott legalább:

- Python-tesztek
- HACS validation
- Home Assistant `hassfest`
- lint
- statikus kódelemzés
- secret scanning
- security tesztek
- dependency audit

---

## Hibabejelentés

Hiba jelentésekor kérlek:

1. írd le a Home Assistant verzióját
2. írd le az integráció verzióját
3. írd le a reprodukálás pontos lépéseit
4. csak anonimizált logot csatolj

### Soha ne küldj

- KRÉTA-jelszót
- access tokent
- refresh tokent
- Authorization headert
- session cookie-t
- oktatási azonosítót
- teljes személyes profilt
- más személyek adatait
- teljes `.storage` fájlt
- valódi KRÉTA API-response dumpot

Ha nem vagy biztos abban, hogy egy log biztonságosan publikálható, előbb anonimizáld.

---

## Jogi megjegyzés

Ez a projekt **közösségi és nem hivatalos**.

A **KRÉTA** név, rendszer, szolgáltatások, arculati elemek és esetleges védjegyek a megfelelő jogosultak tulajdonában állnak.

A név ebben a repositoryban kizárólag a kompatibilitás és a projekt céljának leírására szolgál.

A KRÉTA hivatalos tudásbázisa szerint a mobilalkalmazások által használt API-k nem nyilvánosak, és azok használatára a hivatalos KRÉTA-alkalmazások jogosultak.

Ez a repository:

- nem jelent hivatalos KRÉTA-támogatást
- nem jelent hivatalos API-hozzáférési engedélyt
- nem kapcsolódik hivatalosan a KRÉTA fejlesztőihez
- nem kapcsolódik hivatalosan a KRÉTA üzemeltetőihez

A projekt nem hozzáférés-védelem megkerülésére vagy jogosulatlan fiókhasználatra készült.

---

## Licenc és eredeti projekt

A projekt az MIT licenc alatt elérhető upstream kódra épül.

### Eredeti projekt

[`majorcs/kreta-homeassistant`](https://github.com/majorcs/kreta-homeassistant)

### Eredeti szerző

**Csaba Major**

### Upstream licenc

**MIT License**

Az eredeti MIT copyright- és licencértesítést meg kell őrizni az eredeti kódot vagy annak lényeges részeit tartalmazó terjesztésekben.

A fork új módosításai és fejlesztései ugyanazon repository licencfeltételei szerint kerülnek közzétételre, amennyiben a `LICENSE` fájl másként nem rendelkezik.

> [!IMPORTANT]
> Az upstream projektből származó kód szerzői jogi és licencinformációit ne távolítsd el.

---

## Upstream

Ez a repository a következő projektből indult:

```text
https://github.com/majorcs/kreta-homeassistant
```

---

## Felelősség kizárása

A szoftver **garancia nélkül** kerül közzétételre.

A KRÉTA rendszer:

- API-ja
- hitelesítési folyamata
- adatstruktúrája
- végpontjai
- biztonsági követelményei

előzetes értesítés nélkül megváltozhatnak.

Emiatt az integráció folyamatos működése nem garantálható.

A felhasználó felelőssége, hogy a projektet saját környezetében, saját jogosultságaival és a vonatkozó szabályoknak megfelelően használja.

---

## Közreműködés

Pull requestek, hibajavítások és ötletek szívesen fogadottak.

Közreműködés előtt kérlek:

- ne commitolj valódi KRÉTA-adatokat
- ne commitolj valódi tokeneket
- ne commitolj jelszavakat
- használj anonimizált vagy szintetikus tesztadatokat
- futtasd le a teszteket
- tartsd szem előtt a privacy- és security-first irányelveket

---

## Kapcsolódó projektek

- [Home Assistant](https://www.home-assistant.io/)
- [HACS](https://hacs.xyz/)
- [majorcs/kreta-homeassistant](https://github.com/majorcs/kreta-homeassistant)

---

<p align="center">
  Made for the Home Assistant community.
</p>

<p align="center">
  <strong>With love by Devnixhu</strong>
</p>
