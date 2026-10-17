# Moja svjetla — mobilna aplikacija (Android i iOS)

Mobilna verzija projekta `selver`: aplikacija za Android i iPhone za paljenje, gašenje i prigušivanje Philips Hue svjetala, s promjenama uživo (s prekidača ili iz Hue aplikacije). Aplikacija je napravljena u Vue 3 i spakovana s **Capacitor 8**. Isti kod radi u Chromeu, na Androidu i na iOS-u.

```
Telefon (aplikacija) ──Wi-Fi, HTTP + WebSocket──▶ Backend na računaru ──HTTPS, Hue API V2──▶ Hue Bridge
```

Backend (FastAPI + `aiohue`) i dalje radi na računaru u kućnoj mreži. On čuva API ključ Bridgea, prati Hue event stream i radi sa samopotpisanim certifikatom Bridgea. Telefon zna samo adresu backenda; ključ nikad ne dolazi na telefon. Nema clouda ni prijave.

| Folder | Sadržaj |
| --- | --- |
| `backend/` | FastAPI backend iz `selver` + CORS za aplikaciju + simulirani Bridge (`dev/mock_bridge.py`) |
| `app/` | Vue 3 aplikacija (`src/`) i nativni projekti `android/` i `ios/` |

## 1. Backend na računaru

Potreban je Python 3.11+. U PowerShellu:

```powershell
Set-Location 'C:\Users\jasmi\Desktop\Projekte\selver_mobile\backend'
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

- `--host 0.0.0.0` omogućava telefonu da pristupi backendu. Ako Windows Firewall pita, dozvoli pristup za **privatnu** mrežu.
- Port 8000 koristi i stari `selver` backend. Ako on radi, zaustavi ga ili pokreni ovaj na drugom portu (npr. `--port 8010`) i taj port upiši u aplikaciju.
- Adresa za aplikaciju je lokalna IPv4 adresa računara (`ipconfig` → *IPv4 Address*, npr. `192.168.178.94`) i port, npr. `192.168.178.94:8000`. Bez porta aplikacija koristi 8000.
- Backend nema prijavu. Svako na kućnoj Wi-Fi mreži može upravljati svjetlima, kao i kod pristupa s telefona u starom projektu. Ne prosljeđuj port na ruteru.
- Postavke Bridgea backend sprema u `backend/.env`, kao i ranije. Bridge se povezuje iz aplikacije: **Postavke → Hue Bridge → Promijeni**.

## 2. Pokretanje u Chromeu

Potreban je Node.js 22.12+.

```powershell
Set-Location 'C:\Users\jasmi\Desktop\Projekte\selver_mobile\app'
npm.cmd ci
npm.cmd run dev
```

Otvori **http://127.0.0.1:5173** i upiši adresu servera, npr. `127.0.0.1:8000`. Za izgled telefona u Chromeu otvori DevTools (`F12`) i uključi prikaz uređaja (`Ctrl+Shift+M`). Za razliku od starog projekta nema Vite proxyja: stranica, kao i nativna aplikacija, šalje zahtjeve direktno na unesenu adresu. Backend zato dozvoljava CORS samo za `localhost:5173` i aplikaciju (`capacitor://localhost`, `http://localhost`).

## 3. Android

Potreban je **Android Studio** (dolazi s JDK-om i Android SDK-om; na ovom računaru trenutno je samo stari JDK 8, a on nije dovoljan).

```powershell
Set-Location 'C:\Users\jasmi\Desktop\Projekte\selver_mobile\app'
npm.cmd run android
```

Komanda napravi build, kopira ga u `android/` i otvori Android Studio. Tamo odaberi telefon (USB debugging) ili emulator i klikni **Run**. APK za instalaciju: **Build → Build App Bundle(s) / APK(s) → Build APK(s)**.

Aplikacija koristi `androidScheme: "http"` i `usesCleartextTraffic`, jer backend u kućnoj mreži radi preko običnog HTTP-a.

## 4. iOS (iPhone)

iOS aplikacija se može napraviti samo na **Macu s Xcodeom**. Projekat `ios/` je već generisan. Kopiraj folder na Mac, pa:

```bash
cd selver_mobile/app
npm ci
npm run ios
```

U Xcodeu odaberi svoj tim pod **Signing & Capabilities** i pokreni aplikaciju na iPhoneu. S besplatnim Apple ID-om aplikacija na vlastitom telefonu radi 7 dana; za duže i za App Store potreban je plaćeni Apple Developer račun. Pri prvom pokretanju iOS traži dozvolu za **lokalnu mrežu**: dozvoli je, inače aplikacija ne vidi backend.

## Upravljanje svjetlima

- **Dodir** na pločicu pali ili gasi svjetlo.
- **Prevlačenje lijevo-desno** po pločici mijenja svjetlinu (cijela širina pločice = 100 %). Pločica se puni toplom bojom prema svjetlini. Prevlačenje udesno pali ugašeno svjetlo.
- **Dugme s kolutićem** (gore desno na pločici) otvara panel s velikim kružnim regulatorom. Povuci ručicu po luku ili dodirni luk; ispod su brzi izbori 10–100 % i dugme Upali/Ugasi. Panel se zatvara dugmetom ×, povlačenjem ručke prema dolje, tipkom Esc ili Android dugmetom nazad.
- Kolutić radi i s tastature: strelice ±1 %, Shift+strelica i PageUp/PageDown ±10 %, Home/End 1 % / 100 %.
- Na telefonu kolutić i prevlačenje daju lagane vibracije (haptika).
- Promjena se prikazuje odmah. Dok vučeš, aplikacija šalje najviše jedan zahtjev po svjetlu istovremeno, a novija vrijednost čeka i šalje se odmah nakon prethodne, pa Bridge ne dobija stotine komandi. Svjetla su nezavisna, pa jedno sporo ne blokira druga.
- Svjetla bez dimanja (npr. pametne utičnice) imaju samo paljenje i gašenje.

## 5. Testiranje bez stvarnih svjetala

`backend/dev/mock_bridge.py` je simulirani Hue Bridge sa šest svjetala: jedno je "Nedostupno", a jedna utičnica nema dimanje. Radi na `https://127.0.0.1:443`, prihvata uparivanje dugmetom i šalje promjene kroz event stream.

Za simulirani Bridge pokreni **drugi** backend s vlastitim fajlom postavki (`HUE_ENV_FILE`). Tako stvarni `backend/.env` i tvoj ključ ostaju netaknuti. U dva PowerShell prozora, iz foldera `backend`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe dev\mock_bridge.py
```

```powershell
$env:HUE_ENV_FILE = '.env.mock'
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8011
```

U Chromeu otvori **http://localhost:5173** (ne `127.0.0.1`: to je drugi origin, pa aplikacija tamo pamti drugi server) i upiši server `127.0.0.1:8011`. Zatim Bridge `127.0.0.1` → **Dugme na Bridgeu** → **Poveži Bridge**.

## API

- `GET /api/lights` → `[{"id":"...","name":"Dnevna soba","on":true,"brightness":39.4,"available":true}]`. `brightness` (1–100 %) postoji samo kod svjetala s dimanjem; `available` se izostavlja kad nije poznato.
- `PUT /api/lights/{id}` uz `{"on":true}`, `{"brightness":40}` ili oboje → osvježeni objekat svjetla. Gašenje ide samo preko `on:false`, jer Bridge `brightness: 0` tumači kao najniži nivo.
- `GET`/`POST /api/setup` i WebSocket `/api/ws` su isti kao u `selver`.

## Testovi

```powershell
# backend (iz foldera backend)
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# aplikacija (iz foldera app)
npm.cmd test
npm.cmd run build
```

## Šta je promijenjeno u odnosu na `selver`

**Aplikacija** (`app/src`)
- `App.vue` je razdvojen na komponente `ServerSetup`, `BridgeSetup`, `SettingsScreen`, `LightTile`, `LightSheet` i `BrightnessDial`. Stanje i logika su u `useHue.js`. GET zahtjevi se i dalje ne preklapaju i zastarjeli odgovori se odbacuju.
- Dimanje: prevlačenje po pločici i kružni regulator u donjem panelu (`dial.js` za geometriju). Komande idu kroz red po svjetlu (`commands.js`) s trenutnim prikazom promjene.
- Novi prvi ekran: adresa servera. Pamti se na telefonu (`@capacitor/preferences`) i provjerava preko `GET /api/setup`.
- Mobilni izgled: pločice (dodir = prekidač) s punjenjem prema svjetlini i sjajem sijalice, topli sjaj iza naslova prema broju upaljenih svjetala, čip "Uživo", ekran Postavke, tamna tema, safe-area za notch i status bar, polja od 16 px (bez zumiranja na iOS-u).
- Android dugme "nazad" zatvara panel ili vraća na prethodni ekran.
- Kad aplikacija ode u pozadinu, WebSocket se zatvara; pri povratku se ponovo spaja i osvježava svjetla.
- Zahtjevi imaju rok (12 s; povezivanje Bridgea 30 s), pa pogrešna adresa ne čeka beskonačno.

**Backend**
- Svjetlina: `brightness` u odgovoru i komandi, preko `aiohue` (`dimming`). Validacija je stroga: 1–100, broj (ne string/bool) i najmanje jedno polje. Testovi su u `tests/test_brightness.py`.
- `HUE_ENV_FILE` omogućava drugu instancu s vlastitim postavkama (npr. za simulirani Bridge).
- CORS samo za aplikaciju i Vite dev server (`config.APP_ORIGINS`), uz test `tests/test_cors.py`.
- Uparivanje se u Hue aplikaciji prikazuje kao `local-hue#mobile`.
- Novo: simulirani Bridge `dev/mock_bridge.py` (s dimanjem i utičnicom bez dimanja).
- API, praćenje promjena (SSE → WebSocket) i čuvanje ključa samo na backendu su nepromijenjeni.

## Šta je provjereno

- Backend: 41 test (CORS, svjetlina, `HUE_ENV_FILE`). Aplikacija: 21 test (red komandi, geometrija kolutića, tijelo API zahtjeva, adresa servera, praćenje uživo) i produkcijski build.
- Dimanje u Chromeu sa simuliranim Bridgeom:
  - prevlačenje po pločici (ugašeno → 51 %) i kolutić (25 → 72 %)
  - brzi izbori, tastatura, Ugasi/Upali, zatvaranje panela povlačenjem
  - promjena sa strane uživo (80 → 35 %) i sinhronizacija dvije instance
  - utičnica bez dimanja i nedostupno svjetlo bez kolutića
  - izgled na telefonu u svijetloj i tamnoj temi
- Sa stvarnim Bridgeom: svjetlina se ispravno čita (npr. 100 % i 30 %). Stvarna svjetla nisu prigušivana tokom testa.
- Capacitor projekti `android/` i `ios/` su generisani i sinhronizovani.
- U Chromeu, u širini telefona, sa stvarnim Bridgeom: povezivanje sa serverom i greška za nedostupnu adresu, validacija IP adrese, uparivanje dugmetom, paljenje i gašenje stvarnih svjetala, promjene uživo, Postavke, nazad, pamćenje servera nakon ponovnog učitavanja, pauza i nastavak u pozadini, svijetla i tamna tema.
- **Nije provjereno:** nativni build i pokretanje na Android i iOS uređaju. Na ovom računaru nema Android SDK-a, a iOS zahtijeva Mac.
