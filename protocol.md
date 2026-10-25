Hier is een uitgebreide, gestructureerde Markdown-documentatie op basis van alle informatie die we hebben verzameld: het officiële PHC-protocol (PDF), de ESPHome-broncode, je Node-RED flows en de praktijktesten met de COM-poort. 

Je kunt dit direct als `README.md` op GitHub plaatsen.

---

# PHC-Bus Protocol & Implementatie Documentatie

Deze repository bevat een reverse-engineered documentatie en implementatie van het **PHC-Bus protocol** (Peha Hausautomation). Het doel is om PC's, microcontrollers (ESP32/ESP8266) of Linux-systemen (Raspberry Pi) via een RS485-adapter direct met PHC-modules te laten communiceren.

---

## 1. Fysieke Laag & Hardware

De PHC-bus is fysiek gebaseerd op **RS485**. 

### 1.1. Verbinding
*   **Seriële instellingen:** `19200` baud, `8` databits, `None` pariteit, `2` stopbits (19200 8N2).
*   **Bekabeling:** Gebruik een RS485-adapter (zoals CH340 of FTDI). Verbind `485+` (A) met de `+A` van de bus en `485-` (B) met `-B`.
*   *Let op:* Niet alle USB-RS485 adapters zijn geschikt. Sommige blokkeren de bus volledig, zelfs als ze niet actief gebruikt worden (bekend probleem met bepaalde Digitus DA-70157 versies).

### 1.2. Timing
*   Na het verzenden van een frame moet er minimaal **1 ms** gewacht worden voordat er weer data verzonden wordt.
*   De officiële STM-controller wacht `150 µs` (`TIMING_DELAY`) voordat hij een ACK verstuurt.

---

## 2. Frame Formaat (Data Link Layer)

Elk bericht op de bus heeft de volgende structuur:

`[Adres] [Toggle / Lengte] [Payload (0-127 bytes)] [CRC Low] [CRC High]`

### 2.1. Adres (Byte 0)
Het adres bestaat uit 8 bits, opgedeeld in:
*   **3 bits (MSB):** Device Class (bepaalt het type module).
*   **5 bits (LSB):** Relatief adres (DIP-schakelaars op de module, `0x00` t/m `0x1F`).

| Device Class (Hex) | Module Type |
| :--- | :--- |
| `0x00` | Eingangsmodule (EMD, input) |
| `0x20` | MMC / Infrarotmodule (UIM) |
| `0x40` | Ausgangsmodule (AMD) / Rolladenmodule (JRM) |
| `0x60` | Analog / Funkmodule (FUI) |
| `0x80` | Multimodule |
| `0xA0` | Dimmermodule (DIM) |
| `0xC0` | - |
| `0xE0` | DCF77 |

> **Voorbeeld:** Een AMD/JRM met DIP `5` heeft als adres `0x40 | 0x05 = 0x45`.

### 2.2. Toggle / Lengte (Byte 1)
*   **Bit 7 (MSB):** Toggle-bit.
*   **Bits 0-6:** Lengte van de payload (zonder CRC).

**De Toggle-bit regel:**
*   Bij **normale commando's** (van controller naar module) *moet* de toggle-bit bij elk volgend commando **wisselen** (`0` -> `1` -> `0`). Als je twee keer dezelfde toggle stuurt, ziet de module dit als een retransmit en negeert hij het commando (of stuurt alleen de oude status terug).
*   Bij **bevestigingen (ACK)** en **feedback** behoudt de module de toggle-bit van het oorspronkelijke bericht.

### 2.3. CRC Berekening
De checksum is een CRC16/X25.
*   **Init:** `0xFFFF`
*   **Polynoom:** `0x8408` (omgekeerde van `0x1021`)
*   **XOR out:** `0xFFFF`
*   De CRC wordt verzonden als **Little-Endian** (Low byte eerst, dan High byte).

```python
def phc_crc(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc ^ 0xFFFF
```

---

## 3. Configuratie & Broadcast (Opstarten)

Wanneer een module (EMD, AMD, JRM) opstart of geen configuratie heeft, stuurt deze continu een **Broadcast**-bericht:
`[Adres] 01 FF [CRC Low] [CRC High]`

*Voorbeeld voor AMD DIP 16:* `50 01 FF 8F 53`

De controller (of jouw PC-script) **moet** hierop reageren met een speciaal configuratieframe. Zodra de module dit ontvangt, stopt hij met broadcasten.

### 3.1. AMD / JRM Configuratie
Stuur het volgende frame (5 bytes):
`[Adres] 03 FE 00 FF [CRC]`
*Voorbeeld:* `50 03 FE 00 FF 8C C1`

### 3.2. EMD (Input) Configuratie
De EMD vereist een groter frame (56 bytes). Het vertelt de module welke kanalen actief zijn en welke functies ze hebben. 
Formaat: `[Adres] 34 FE 00 00 00 [16 x 3 bytes] [CRC]`
*   De 16 x 3 bytes bepalen per kanaal de functies (standaard: `Ein>0`, `Aus<0`, `Aus>1`).
*   *Opmerking:* De ESPHome-implementatie stuurt altijd 16 kanalen, ook als ze niet fysiek zijn aangesloten.

---

## 4. Module Commando's (Payload)

### 4.1. Ausgangsmodule (AMD) - Relais
Bij AMD is de payload opgebouwd uit: **3 bits kanaal (MSB)** en **5 bits functie (LSB)**.
Formule: `(kanaal << 5) | functie`

| Functie (Hex) | Betekenis | Bytes | Opmerking |
| :--- | :--- | :--- | :--- |
| `0x02` | Ein (Aan) | 1 | |
| `0x03` | Aus (Uit) | 1 | |
| `0x04` | An Lock | 1 | |
| `0x05` | Aus Lock | 1 | |
| `0x06` | **Umschalten (Toggle)** | 1 | Meest gebruikt voor schakelaars |
| `0x07` | Unlock | 1 | |
| `0x08` | An verzögert | 3 | + 2 bytes tijd (100ms eenheden) |
| `0x09` | Aus verzögert | 3 | + 2 bytes tijd |
| `0x0A` | An mit Timer | 3 | + 2 bytes tijd |
| `0x0B` | Aus mit Timer | 3 | + 2 bytes tijd |
| `0x0C` | Umschalten verzögert | 3 | + 2 bytes tijd |
| `0x0D` | Umschalten mit Timer | 3 | + 2 bytes tijd |

**Status opvragen:**
Stuur een commando met payload `0x01`:
`[Adres] 01 01 [CRC]` (of `81 01` afhankelijk van toggle).

**Antwoord (ACK) van AMD:**
De module antwoordt met 2 bytes payload: `[00] [Status_Byte]`.
*Voorbeeld:* `40 02 00 04 XX XX` -> `0x04` (`00000100`) betekent dat kanaal 2 aan staat (bit 2 = 1).

### 4.2. Rolladenmodule (JRM) - Rolluiken
Payload opbouw: **3 bits kanaal** en **5 bits functie**.
Formule: `(kanaal << 5) | functie`

| Functie (Hex) | Betekenis | Bytes | Opmerking |
| :--- | :--- | :--- | :--- |
| `0x02` | Stop | 1 | |
| `0x03` | Umschalten heben stop | 1 | |
| `0x04` | Umschalten senken stop | 1 | |
| `0x05` | Heben (Omhoog) | 4 | + 1 byte prio + 2 bytes tijd |
| `0x06` | Senken (Omlaag) | 4 | + 1 byte prio + 2 bytes tijd |
| `0x07` | Flip auf | 1 | |
| `0x08` | Flip ab | 1 | |
| ... | ... | ... | ... |

### 4.3. Eingangsmodule (EMD) - Knoppen
Payload opbouw: **4 bits kanaal** en **4 bits functie**.
Formaat: `(kanaal << 4) | functie`

*   **Van Controller naar EMD (LED's):**
    *   `0x02` = LED Ein
    *   `0x03` = LED Aus
*   **Van EMD naar Controller (indrukken):**
    *   `0x02` = Ein > 0 (kort indrukken)
    *   `0x03` = Aus < 0 (loslaten)
    *   `0x04` = Ein > 1 (lang indrukken)
    *   `0x05` = Aus > 1 (loslaten na lang indrukken)
    *   `0x06` = Ein > 2

---

## 5. Praktijkvoorbeelden (Hex Commando's)

Hieronder voorbeelden voor het aansturen van een **AMD (Relais) op adres `0x45` (DIP 5)**.

### Opstarten / Broadcast Stoppen
*   **TX:** `45 03 FE 00 FF [CRC]`

### Status Opvragen
*   **TX:** `45 01 01 [CRC]`
*   **RX:** `45 02 01 02 [CRC]` *(Betekenis: ACK + Status 0x02 = Kanaal 1 staat AAN)*

### Kanaal 0 Omschakelen (Toggle)
*   **TX (toggle=0):** `45 01 06 [CRC]`
*   **TX (toggle=1):** `45 81 06 [CRC]`
*   **RX:** `45 02 00 01 [CRC]` *(Status 0x01 = Kanaal 0 staat nu AAN)*

### Kanaal 2 Inschakelen met 5 seconden vertraging
*   Payload: `(2 << 5) | 0x08` = `0x48`
*   Tijd: 5 sec = 50 (decimaal) = `0x0032` (Little Endian: `32 00`)
*   **TX:** `45 03 48 32 00 [CRC]`

---

## 6. Node-RED & ESPHome Implementatie

### 6.1. ESPHome
Binnen ESPHome wordt de PHC-bus aangestuurd via een custom component. Hierbij wordt gebruik gemaakt van een UART-component (19200 8N2). Omdat de ESP32 UART-buffer vertraging kan opleveren bij ACK-berichten, is het essentieel om de `RxFIFOFull` op `1` te zetten (zie `PHCController.cpp`). Dit zorgt voor immediate parsing van inkomende data.

### 6.2. Node-RED / STM32 USB Kabel
In de Node-RED flow van de "officiële Peha eenheid" (STM32) wordt een speciaal protocol gebruikt over USB:
*   Commando's worden ingepakt tussen `C0` (start) en `C1` (eind).
*   Hierbij wordt een startheader gebruikt: `C0 FE 00 06 00` (voor outputs) of `C0 FE 00 21 00` (voor inputs).
*   Byte-stuffing: Als de CRC de bytes `C0` of `C1` bevat, worden deze ge-escaped (`C0` -> `7D E0`, `C1` -> `7D E1`, `7D` -> `7D 5D`).
*   *Let op:* Dit `C0 ... C1` protocol is **specifiek voor de USB-poort van de officiële STM-module**, niet voor de RS485 bus zelf!

---

## 7. Tips & Troubleshooting

*   **Mijn relais schakelt maar 1 keer:** Vergeet niet de **toggle-bit** te wisselen bij elk nieuw commando. Als je `01` stuurt, moet het volgende commando `81` zijn.
*   **Mijn module blijft `01 FF` sturen:** Je hebt de broadcast nog niet gestopt. Stuur het configuratieframe `03 FE 00 FF`.
*   **De CRC klopt niet:** Controleer of je de CRC berekent over alle bytes *tot* de CRC (dus inclusief adres en toggle/lengte byte). De CRC wordt little-endian verzonden.
*   **Sommige bytes worden niet herkend (framing):** Als je PC-terminal willekeurige data laat zien, kan het zijn dat je halverwege een frame begint te lezen. Gebruik een script dat zoekt naar de startbyte en de CRC valideert (zie de Python-scripts in deze repo).
*   **USB-RS485 Adapter blokkeert de bus:** Gebruik een adapter met een FTDI-chip of een goede CH340. Vermijd adapters die de lijnen actief laag houden als ze niet gebruiken.

---
*Gebaseerd op de officiële PHC-Protokoll PDF, ESPHome broncode, en praktijktesten met Node-RED en Python.*
