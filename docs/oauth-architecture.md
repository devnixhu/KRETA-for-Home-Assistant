# KRÉTA OAuth architektúra

## Vizsgálati eredmény

A jelenleg vizsgált KRÉTA mobil OAuth-protokoll a `kreta-ellenorzo-student-mobile-ios` kliensazonosítót, `response_type=code` értéket, S256 PKCE-t, valamint a `https://mobil.e-kreta.hu/ellenorzo-student/prod/oauthredirect` visszatérési URI-t használja. A scope az `openid`, `email`, `offline_access` és a mobil KRÉTA API-khoz szükséges publikus scope-ok együttese.

A Firka minden bejelentkezéshez véletlen code verifiert, challenge-et és state/nonce értéket készít. A hivatalos KRÉTA oldalt WebView-ban nyitja meg, majd a mobil visszatérési útvonalra történő navigációt még a betöltés előtt elfogja. Az authorization code-ot ugyanazzal a code verifierrel küldi a `https://idp.e-kreta.hu/connect/token` végpontra.

## Home Assistant callback

Nem találtunk bizonyítékot arra, hogy a KRÉTA mobil kliens regisztrációja tetszőleges Home Assistant callback URI-t elfogadna. A működő referencia rögzített mobil redirect URI-t használ. Emiatt a megvalósítás nem állítja, hogy egy Home Assistant callback támogatott, és nem küld authorization code-ot külső proxyhoz.

A Home Assistant nem tudja a Firka WebView-jához hasonlóan elfogni egy általános külső böngésző navigációját. A natív `async_external_step` csak akkor tud automatikusan befejeződni, ha az OAuth szolgáltató vissza tud irányítani egy Home Assistant által kezelt callbackre. A rögzített mobil URI mellett ez a feltétel nem teljesül.

## Kiválasztott megoldás

A config flow Home Assistant external stepet ad vissza, amely egy új böngészőlapon egy öt percig érvényes, aláírt helyi indító URL-t nyit meg. Az indító egy kriptográfiailag véletlen, egyszer használható azonosítót fogyaszt el, ismét ellenőrzi a célcímet a hálózati allowlisttel, majd HTTP 302 válasszal a hivatalos KRÉTA belépési URL-re irányít. A helyi URL nem tartalmaz authorization code-ot, tokent, jelszót, kétlépcsős kódot vagy PKCE verifiert.

A felhasználó közvetlenül a KRÉTA oldalán adja meg a felhasználónevet, a jelszót és a kétlépcsős kódot. A végső mobil redirect URL-t visszamásolja a Home Assistantba.

Az integráció elfogadás előtt ellenőrzi a HTTPS sémát, a pontos `mobil.e-kreta.hu` hostot, a rögzített visszatérési útvonalat és a kriptográfiailag véletlen state értéket. Ezután az authorization code-ot a csak memóriában élő PKCE verifierrel cseréli tokenekre. Az authorization code, state, nonce, verifier, access token és ID token nem kerül tartós tárolásba. Tartósan csak a refresh token és egy hash-elt, nem azonosító account key marad meg.

## Migráció

A régi config entryből a jelszó a 2-es verzióra migráláskor törlődik. Ha a korábbi refresh token érvényes, a működés bejelentkezés nélkül folytatódik. Lejárt vagy visszavont refresh token esetén a Home Assistant új böngészős OAuth-bejelentkezést indít. A sikeres újrahitelesítés után a régi felhasználói azonosító alapú tárolókulcsot az új, ID token subjectből képzett hash váltja fel.
