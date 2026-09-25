# KRÉTA kliens Home Assistanthoz

Nem hivatalos, közösségi Home Assistant-integráció, amely egy reszponzív KRÉTA-kliensfelületet, automatizálható eseményeket, naptárakat és háttér-entitásokat biztosít.

> [!IMPORTANT]
> A projekt nem áll kapcsolatban a KRÉTA vagy a Home Assistant fejlesztőivel. A KRÉTA által használt, nem nyilvános mobil API-k előzetes értesítés nélkül változhatnak. A használat saját felelősségre történik.

## Mit nyújt?

Az elsődleges kezelőfelület a beépített `custom:kreta-dashboard-card`. Ez nem egyetlen nagy JSON-szenzort jelenít meg, hanem közvetlenül az integráció normalizált, helyi gyorsítótárából kérdezi le az adatokat.

A kliens nézetei:

- áttekintés az aktuális és következő órával
- mai, holnapi és heti órarend
- jegyek kereséssel, tantárgyszűréssel, dátumszűréssel, rendezéssel és lapozással
- dolgozatok és házi feladatok
- órarendváltozások, helyettesítések és elmaradt órák
- hiányzások
- tanévi események
- több KRÉTA-fiók grafikus kiválasztása
- asztali oldalsáv és mobil, érintésbarát navigáció
- magyar és angol felület, Home Assistant-téma támogatással

A Home Assistant-entitások megmaradnak háttér- és automatizálási felületként. Ide tartozik többek között az aktuális és következő óra, az iskolai állapot, az órarendi naptár, a frissítés gombja, az összesítők és az opcionális részletes entitások.

## Telepítés

### HACS

1. A HACS Integrations részében adj hozzá egy egyedi repositoryt.
2. Repository: `https://github.com/devnixhu/KRETA-for-Home-Assistant`
3. Típus: Integration
4. Telepítés után indítsd újra a Home Assistantot.
5. A Beállítások → Eszközök és szolgáltatások oldalon add hozzá a KRÉTA-integrációt.

### Kézi telepítés

Másold a `custom_components/kreta` könyvtárat a Home Assistant `/config/custom_components/kreta` útvonalára, majd indítsd újra a Home Assistantot.

## Bejelentkezés és 2FA

1. Add meg az intézményi azonosítót.
2. A Home Assistant egy rövid élettartamú, aláírt helyi indítócímen keresztül megnyitja a hivatalos KRÉTA bejelentkezési oldalt.
3. A felhasználónevet, jelszót és szükség esetén az egyszer használatos 2FA-kódot kizárólag a KRÉTA oldalán add meg.
4. A sikeres belépés végén másold vissza a teljes visszatérési URL-t a Home Assistant űrlapjára.

Az integráció ugyanahhoz a mobil OAuth-klienshez tartozó `client_id`, visszatérési útvonal és PKCE-adatok konzisztenciáját ellenőrzi. Nem keveri ezt az EduID/KIFU folyamattal. A hálózati engedélylista, a TLS-ellenőrzés, a callback hostja, útvonala és `state` értéke fail-closed módon érvényesül.

A jelszó és a 2FA-kód nem kerül a Home Assistantba, nem kerül tárolásra és nem kerül naplózásra. Az OAuth-kód, tokenek, cookie-k és Authorization headerek szintén ki vannak zárva a naplókból és a diagnosztikából.

## A KRÉTA-kliens hozzáadása

Az integráció a klienskártya JavaScript-erőforrását automatikusan regisztrálja. A dashboard szerkesztőjében keresd a **KRÉTA kliens** kártyát, vagy használd ezt a minimális YAML-konfigurációt:

```yaml
type: custom:kreta-dashboard-card
view: overview
```

Ha csak egy KRÉTA-fiók van beállítva, a kártya automatikusan kiválasztja. Több fióknál a grafikus kártyaszerkesztőben választható ki a tanuló. Ugyanott állítható a kezdőnézet, a megjelenített adatok, az időformátum, a sűrűség, a heti és mobil elrendezés, valamint a kiemelőszín.

## Adatfrissítés és gyorsítótár

- A koordinátor az egyes KRÉTA-adatcsoportokat egymástól elkülönítve frissíti.
- Egy opcionális végpont hibája nem teszi használhatatlanná a már elérhető adatokat.
- A lekérések dátumtartományai korlátozott darabokra vannak bontva.
- A közeljövő gyakran frissül, a távoli jövő csak a még nem lefedett tartományban töltődik le.
- A helyi gyorsítótár fiókonként elkülönül, normalizált adatokat tartalmaz, és hálózati hiba esetén biztonságos visszaesést ad.
- A kézi módhoz a frissítési időköz `0` percre állítható.
- Az előzmény- és jövőtartomány legfeljebb 52 hétre állítható.

## Automatizálások

Az integráció eszközindítókat biztosít új jegyhez, új házi feladathoz, új dolgozathoz, órarendváltozáshoz, helyettesítéshez, óra kezdetéhez és végéhez, valamint a tanítási nap végéhez.

Elérhető események többek között:

- `kreta_new_grade`
- `kreta_new_homework`
- `kreta_new_message`
- `kreta_new_absence`
- `kreta_new_test`
- `kreta_timetable_change`
- `kreta_substitution`
- `kreta_lesson_cancelled`
- `kreta_room_changed`
- `kreta_teacher_changed`
- `kreta_lesson_started`
- `kreta_lesson_finished`
- `kreta_break_started`
- `kreta_school_started`
- `kreta_school_finished`

Az eseményadatok csak a működéshez szükséges, normalizált mezőket tartalmazzák. A nyers KRÉTA-válasz nem kerül továbbításra.

Szolgáltatások:

- `kreta.refresh`
- `kreta.get_day`
- `kreta.get_week`
- `kreta.get_grades`
- `kreta.get_tests`
- `kreta.get_homework`

## Biztonság és adatvédelem

- szigorú host-, útvonal- és redirect-engedélylista
- kötelező TLS-tanúsítvány-ellenőrzés
- OAuth Authorization Code + PKCE
- fiókonként elkülönített token- és adatgyorsítótár
- jelszó és 2FA-kód tartós tárolása nélkül
- tokenek, kódok, cookie-k, hitelesítési fejlécek és személyes profiladatok naplózása nélkül
- adatcsoportonkénti, személyes adatot nem tartalmazó hibadiagnosztika
- korlátozott WebSocket-lekérdezések és válaszméretek

A működéshez szükséges OAuth-tokeneket a Home Assistant saját `.storage` rendszerében kezeli az integráció. A `.storage` könyvtárat soha ne oszd meg és ne tedd közzé.

## Hibakeresés

Ha a beállítás „KRÉTA data update failed” hibával áll meg, az anonimizált naplóban keresd a `KRÉTA API operation failed` bejegyzést. Ez tartalmazhatja a művelet nevét, HTTP-metódust, engedélyezett hostot és útvonalat, státuszkódot, kivételosztályt és rövid, tisztított leírást. Hitelesítési adatok vagy tanulói személyes adatok nem jelenhetnek meg benne.

Hibajegyhez add meg a Home Assistant és az integráció verzióját, a reprodukálás lépéseit és csak anonimizált naplórészletet. Soha ne küldj jelszót, 2FA-kódot, tokent, callback URL-t, oktatási azonosítót, cookie-t vagy `.storage` fájlt.

## Fejlesztés és ellenőrzés

```bash
python -m pip install -r requirements-dev.txt -r requirements-ha.txt
pytest
ruff check .
ruff format --check .
```

A repository CI-je HACS validation és Home Assistant hassfest ellenőrzést is futtat.

## Korlátok

- Ez nem hivatalos kliens, ezért a KRÉTA szerveroldali változásai megszakíthatják a működést.
- A valódi KRÉTA-fiókos működés csak élő fiókkal és élő szerverválaszokkal igazolható teljesen.
- A böngészős OAuth-visszatérés jelenleg kézi URL-visszamásolást használ, mert a mobil OAuth-kliens rögzített callback címe nem a Home Assistant címe.
- Az integráció olvasási és automatizálási célú; nem helyettesíti a hivatalos KRÉTA alkalmazás minden funkcióját.

## Licenc és eredet

A projekt a [`majorcs/kreta-homeassistant`](https://github.com/majorcs/kreta-homeassistant) MIT-licencű projektjéből indult. A licenc- és szerzői jogi értesítések a [LICENSE](LICENSE) fájlban találhatók.

A KRÉTA név és a kapcsolódó védjegyek a jogosultjaik tulajdonában állnak; itt kizárólag a kompatibilitás leírására szolgálnak.
