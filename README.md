# FlexModbus

Vrij configureerbare Modbus TCP-integratie voor Home Assistant. Geen vaste registerlijst per apparaat, zoals bij de meeste kant-en-klare Modbus-integraties — je stelt zelf in welke registers je wilt uitlezen (als sensor) of instellen (als number), met het datatype, de byte-volgorde, eenheid en schaling die bij jouw apparaat horen.

Gebouwd en uitgebreid tijdens het aansluiten van een SolarEdge- en een Solplanet-omvormer via Waveshare RS485-naar-Ethernet-gateways, maar niet aan die apparaten gebonden: alles is instelbaar.

## Kenmerken

- **Registers volledig zelf configureren** — geen vaste apparaatprofielen. Holding- en input-registers, met adres, slave-ID, datatype en byte-volgorde.
- **Datatypes**: `uint16`, `int16`, `uint32`, `int32`, `float32`, en tekst (`string16` / `string32`, SunSpec-notatie: het aantal registers, dus resp. max. 32 en 64 tekens).
- **Byte-volgorde**: ABCD (big endian), CDAB, BADC, DCBA (little endian) — voor 32-bit waarden.
- **Sensor- én Number-entiteiten**: alleen-lezen waarden of schrijfbare instelwaarden (Number kan alleen op holding-registers).
- **Entiteitscategorie**: normaal, diagnostiek of configuratie (dat laatste alleen voor Number).
- **Waardenlijst voor statuscodes**: zet een ruwe code (bijvoorbeeld `0`, `1`, `2`) om naar leesbare tekst (`Wait`, `Normal`, `Fault`), als nette Home Assistant-enum-sensor met een keuzelijst van mogelijke statussen. Alleen voor Sensor; niet voor tekst- of float32-registers.
- **Bitvlaggen voor foutstatusregisters (B16/B32)**: toon welke losse bits in één register actief zijn als leesbare, kommagescheiden tekst (bijvoorbeeld "Communicatiefout, Celspanning te hoog"). Alleen voor Sensor met `uint16`/`uint32`, niet te combineren met een waardenlijst op hetzelfde register.
- **Importeren vanuit YAML**: zet sensoren uit de ingebouwde Home Assistant Modbus-integratie (`modbus:`-blok in `configuration.yaml`) in één keer om naar FlexModbus-registers, met een overzicht vooraf van wat wel en niet kan worden overgenomen.
- **Twee verbindingstypen**: gewone Modbus TCP, of RTU-framing over TCP voor transparante seriële gateways.
- **Eén centrale, gedeelde verbinding** per apparaat: alle registers worden in één ronde na elkaar uitgelezen, met een gedeelde connectie in plaats van dat elke entiteit los polt.
- **Per apparaat instelbaar**: poll-interval, pauze tussen verzoeken, en hoe lang de verbinding na inactiviteit open blijft staan voordat hij zelf gesloten wordt.
- **Robuuste foutafhandeling**: een los gemist antwoord houdt de laatste waarde vast (i.p.v. meteen "niet beschikbaar"); pas na een paar mislukkingen op rij wordt een entiteit onbeschikbaar. Antwoorden van een verkeerd slave-ID of met een verkeerd aantal registers (bijvoorbeeld door ander verkeer op dezelfde bus) worden herkend en genegeerd.
- **Optioneel**: bekende, onschadelijke pymodbus-foutmeldingen (die ontstaan als een apparaat ongevraagd eigen verkeer op de lijn stuurt) uit het Home Assistant-log filteren.
- Nederlandse en Engelse vertaling.

## Vereisten

- Home Assistant 2024.8 of nieuwer (gebruikt `ConfigEntry.runtime_data` en de reconfigure-flow; ouder is niet getest).
- `pymodbus` versie 3.8 of hoger. Voor de nieuwste `device_id`-parameter is 3.10+ nodig; op oudere versies valt de integratie automatisch terug op de oudere `slave`-parameter.

## Installatie

### Via HACS (aanbevolen)

1. HACS → **Integraties** → menu (⋮) rechtsboven → **Aangepaste repositories**.
2. Voeg deze repository-URL toe, categorie **Integratie**.
3. Zoek naar "FlexModbus" en installeer.
4. Herstart Home Assistant.

### Handmatig

1. Kopieer de map `custom_components/flexmodbus` naar de `custom_components`-map van je Home Assistant-configuratie.
2. Herstart Home Assistant.

## Eerste apparaat toevoegen

**Instellingen → Apparaten & diensten → Integratie toevoegen → FlexModbus.**

| Veld | Uitleg |
|---|---|
| Naam | Vrije naam voor dit apparaat, bijvoorbeeld "Omvormer". |
| IP-adres (host) | Adres van het apparaat of de RS485-naar-Ethernet-gateway. |
| Poort | Meestal 502. |
| Verbindingstype | **Modbus TCP**: het normale protocol, voor apparaten met een eigen netwerkaansluiting of een gateway in de modus "Modbus TCP to RTU". **RTU over TCP**: alleen voor een gateway die transparant doorgeeft (protocol "None"/"Transparent"), waarbij ruwe RTU-frames over de kale TCP-verbinding gaan. |
| Poll-interval | Hoe vaak alle registers in één ronde worden uitgelezen (5-300 s, standaard 15 s). Hoger zetten bij een traag of instabiel apparaat. |
| Pauze tussen verzoeken | Wachttijd op de bus tussen twee verzoeken (0-5000 ms, standaard 350 ms). Verhogen als een druk apparaat in de war raakt van snel achter elkaar pollen. |
| Verbinding sluiten na inactiviteit | 0 = nooit automatisch sluiten (standaard, snelst). Hoger dan 0: de verbinding wordt na zoveel seconden inactiviteit gesloten en bij de volgende actie weer opgebouwd — een middenweg tussen altijd open (kwetsbaarder voor ongevraagd verkeer van het apparaat) en na elke ronde meteen dicht (meer overhead, kan pollen merkbaar vertragen bij een trage gateway). |
| Bekende pymodbus-storingsmeldingen uit het log houden | Verbergt specifiek bekende, onschadelijke meldingen (zie hieronder bij Problemen oplossen). Geldt voor heel Home Assistant zolang minstens één apparaat dit aan heeft staan. |

De verbinding wordt bij het opslaan getest; lukt dat niet, dan blijft het formulier openstaan met een foutmelding.

## Registers beheren

Ga naar de integratie → **Configureren** (het tandwiel-icoon) om registers toe te voegen, te bewerken of te verwijderen.

| Veld | Uitleg |
|---|---|
| Naam | Naam van de entiteit. |
| Soort entiteit | Sensor (alleen lezen) of Number (schrijfbaar, alleen holding-registers). |
| Categorie | Normaal, Diagnostiek, of Configuratie (alleen bij Number). |
| Apparaatklasse | Bepaalt icoon en eenheid-conventie in Home Assistant (vermogen, energie, temperatuur, ...). |
| Statusklasse | Voor sensoren: "Live meting" (schommelt) of "Totaal oplopend" (telt alleen op, voor energiemeters). |
| Registertype | Holding of Input. Een Number kan alleen Holding zijn. |
| Registernummer | Zoals in de handleiding van het apparaat — 1 is het eerste register (1-gebaseerd, niet 0-gebaseerd). |
| Slave-/unit-ID | Het Modbus-adres van het apparaat op de bus (vaak 1). |
| Datatype | Zie hierboven bij Kenmerken. Bij een tekst-type (`string16`/`string32`) vervallen byte-volgorde, vermenigvuldiger, offset, eenheid en klassen automatisch. |
| Byte-volgorde | Alleen van belang bij 32-bit waarden (2 registers). Zie hieronder bij Problemen oplossen als een waarde er compleet naast zit. |
| Eenheid | Bijvoorbeeld `W`, `kWh`, `°C`. Verplicht zodra er een apparaatklasse is gekozen die een eenheid vereist. |
| Vermenigvuldiger / offset | Waarde = ruwe registerwaarde × vermenigvuldiger + offset. |
| Minimum / maximum / stapgrootte | Alleen voor Number. |
| Waardenlijst (optioneel) | Eén regel per code, in de vorm `code: label`, bijvoorbeeld:<br>`0: Wait`<br>`1: Normal`<br>`2: Fault`<br>`4: Checking`<br>Laat leeg voor een gewoon getal. Alleen bij Sensor, niet bij tekst- of float32-registers. Een code die niet in de lijst staat, wordt getoond als "Onbekend (code)". |
| Bitvlaggen (optioneel) | Voor B16/B32-registers (losse aan/uit-vlaggen in één getal, zoals foutstatusregisters). Eén regel per bit, in de vorm `bitnummer: label`, bijvoorbeeld:<br>`0: Communicatiefout`<br>`1: Celspanning te hoog`<br>`3: Temperatuur te hoog`<br>Toont alle actieve bits, gescheiden door komma's ("Geen actieve vlaggen" als er geen actief zijn); een niet-benoemde actieve bit verschijnt als "bitN (onbekend)". Alleen bij Sensor met datatype `uint16` (bit 0-15) of `uint32` (bit 0-31), en niet samen met een waardenlijst op hetzelfde register. |

Wijzigingen aan registers herladen de integratie automatisch.

## Verbinding wijzigen

Integratie → **⋮ → Opnieuw configureren** om host, poort, verbindingstype, poll-interval, pauze of het log-filter later aan te passen. Je registers blijven behouden.

## Importeren vanuit de ingebouwde Home Assistant Modbus-integratie

Heb je al een `modbus:`-blok in je `configuration.yaml`? Je kunt de sensoren daaruit importeren in plaats van ze allemaal opnieuw met de hand in te voeren.

Integratie → **Configureren → Importeren vanuit YAML**. Plak het `modbus:`-blok (of alleen de relevante hub) en je krijgt eerst een overzicht te zien — wat wordt geïmporteerd, wat wordt overgeslagen en waarom — voordat er iets wordt opgeslagen.

**Wat wordt omgezet:**
- Sensoren met datatype `int16`, `uint16`, `int32`, `uint32`, `float32` of `float` (standaard `int16` als je niets opgeeft, zoals in de originele YAML).
- `swap: word` → byte-volgorde CDAB, `swap: byte` → BADC, `swap: word_byte` → DCBA, geen `swap` → ABCD.
- `scale` → vermenigvuldiger, `offset` → offset, `slave`/`device_address` → slave-ID. Het adres wordt automatisch met 1 opgehoogd (Home Assistant telt vanaf 0, FlexModbus vanaf 1).
- Reeds bestaande registers (zelfde slave/adres/type) worden herkend en niet dubbel toegevoegd.

**Wat wordt overgeslagen** (met reden getoond in het overzicht):
- 64-bit types (`int64`, `uint64`, `float64`), `string`/`custom`-registers met een variabel aantal registers.
- `binary_sensors`, `switches`, `covers` en `climates` — deze zijn gebaseerd op coils, en FlexModbus werkt alleen met holding- en input-registers.
- Een `count` die niet bij het datatype past.
- `precision` wordt niet overgenomen (FlexModbus rondt altijd af op 3 decimalen); dit register wordt wel geïmporteerd, met een opmerking in het overzicht.

Deze importfunctie verandert niets aan je bestaande `configuration.yaml` — die kun je daarna zelf verwijderen als je volledig op FlexModbus overstapt.

## Problemen oplossen

**Alle registers geven "geen antwoord".**
Controleer in deze volgorde: het verbindingstype (Modbus TCP vs. RTU over TCP — dit is de meest voorkomende oorzaak), het slave-ID, en of de registeradressen kloppen (1-gebaseerd).

**Eén specifieke 32-bit waarde is compleet fout, andere niet.**
Vrijwel altijd de verkeerde byte-volgorde. Probeer de andere drie opties.

**"request ask for id=X but got id=Y" / "Unable to decode frame" / "Fatal error: protocol.data_received() call failed" in het log.**
Dit betekent dat er iets anders dan onze eigen verzoeken op dezelfde lijn verschijnt — bijvoorbeeld een omvormer die intern naar een niet-aangesloten meter zoekt, of een gateway met meerdere gelijktijdige clients (multi-host) aan. De integratie herkent en negeert deze vreemde antwoorden zelf al; je sensoren blijven gewoon bijgewerkt. Wil je dit niet in het log zien, zet dan bij het apparaat **"Bekende pymodbus-storingsmeldingen uit het log houden"** aan. Komt de melding heel vaak voor (elke paar seconden), zoek dan naar de bron: een instelling op het apparaat zelf die naar een niet-bestaande meter zoekt, of een gateway-instelling zoals "multi-host".

**Metingen worden trager na het instellen van "verbinding sluiten na inactiviteit".**
Bij een lage waarde (bijvoorbeeld 0-5 s) wordt de verbinding vrijwel elke pollronde opnieuw opgebouwd. Sommige gateways zijn daar traag mee. Zet de waarde hoger dan je poll-interval om de verbinding feitelijk continu open te houden, met alleen een vangnet voor langere periodes van stilte.

**pymodbus-versie ouder dan 3.10.**
De integratie herkent dit automatisch en gebruikt dan de oudere `slave=`-parameter in plaats van `device_id=`. Geen actie nodig.

## Bijdragen

Issues en pull requests zijn welkom via de issue tracker van deze repository.

## Licentie

MIT — zie [LICENSE](LICENSE).
