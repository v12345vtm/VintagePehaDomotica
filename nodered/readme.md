# Peha PHC Bus Protocol - Complete Reverse Engineering

Welkom bij de complete documentatie van het **Peha PHC-bus protocol**. Dit project bevat de volledige reverse-engineering van de communicatie tussen de PHC-controller (CTM), Input modules (IMD), Output modules (AMD) en Rolluik modules (JRM).

De communicatie verloopt via een dubbele USB-architectuur:
1. **Tx (Zenden):** Via de officiële STM-stuureenheid (bijv. `/dev/ttyACM0`). Vereist het `C0 ... C1` protocol met byte-stuffing.
2. **Rx (Ontvangen):** Via een passieve RS485-dongle op de bus (bijv. `/dev/ttyUSB0`). Levert ruwe bus-data die door een CRC-parser wordt geanalyseerd.

---

## 1. Hardware & Fysieke Laag
*   **Baudrate:** 19200
*   **Data bits:** 8
*   **Pariteit:** None
*   **Stopbits:** 2

### 1.1. Adressering (DIP-switches)
De PHC-bus gebruikt een 8-bit adres. De hoogste 3 bits bepalen de moduleklasse, de laagste 5 bits zijn de fysieke DIP-schakelaars (0-31).

| Hex Bereik | Module Type | Basis Hex | DIP formule |
| :--- | :--- | :--- | :--- |
| `0x00` - `0x1F` | **IMD / EMD** (Ingangen) | `0x00` | `0x00 + DIP` |
| `0x20` - `0x3F` | MMC / IR / Busschakelaars | `0x20` | `0x20 + DIP` |
| `0x40` - `0x5F` | **AMD** (Relais) & **JRM** (Rolluiken) | `0x40` | `0x40 + DIP` |
| `0xA0` - `0xBF` | DIM (Dimmers) | `0xA0` | `0xA0 + DIP` |

*Voorbeeld:* Een rolluikmodule met DIP-schakelaar op stand `3` heeft bus-adres `0x43`.

---

## 2. STM-USB Protocol (Tx naar de bus)

Wanneer je een commando naar de STM-stuureenheid stuurt, moet dit verpakt worden in een speciaal USB-frame. 

**Structuur:** `[C0] [Header] [Data] [CRC_lo] [CRC_hi] [C1]`

*   **Byte-Stuffing:** Als de data of CRC de bytes `C0`, `C1` of `7D` bevat, moeten deze ge-escaped worden:
    *   `C0` -> `7D E0`
    *   `C1` -> `7D E1`
    *   `7D` -> `7D 5D`
*   **CRC:** CRC16/X25 (Init `0xFFFF`, Polynoom `0x8408`, XOR-out `0xFFFF`).

### 2.1. Headers
De STM verwacht verschillende headers, afhankelijk van wat je wilt doen:

| Header | Doel | Lengte-byte aanwezig? |
| :--- | :--- | :--- |
| `FE 00 06 00` | Status opvragen (alle modules) | Ja (meestal `01`) |
| `FE 00 06 00` | Commando naar Output (AMD/JRM) | Ja (afhankelijk van payload) |
| `FE 00 21 00` | Commando naar Input (IMD) | **Nee** (Direct adres + payload) |

*Voorbeeld van een IMD commando (Kanaal 13, Kort indrukken op adres 02):*
`C0 FE 00 21 00 02 D2 [CRC] C1`

---

## 3. De RS485 Bus (Rx van de bus)

Data die van de bus komt is ruw en moet geparseerd worden. De structuur van een bus-frame is:
`[Adres] [Toggle/Lengte] [Payload] [CRC_lo] [CRC_hi]`

*   **Toggle-bit:** Zit in bit 7 van byte 1. Moet bij elk nieuw commando wisselen om hertransmissies te voorkomen.
*   **Lengte:** De laagste 7 bits van byte 1 bepalen de payload-lengte.

---

## 4. Module Specifieke Protocollen

### 4.1. IMD (Input Module - Ingangen)
Input modules hebben 16 ingangen (knoppen) en optioneel 8 of 16 LEDs.

**Knopdruk (Event):** 
*   Lengte: 1 byte.
*   Payload: `(Kanaal << 4) | Functie`.
*   Kanaal: 0 t/m 15 (4 bits).
*   Functie: 2 t/m 7 (4 bits).

| Functie (Hex) | Betekenis | Omschrijving |
| :--- | :--- | :--- |
| `0x02` | Aan > 0 seconden | Kort ingedrukt |
| `0x03` | Uit < 1 seconde | Losgelaten (kort) |
| `0x04` | Aan > 1 seconde | Lang ingedrukt |
| `0x05` | Uit > 1 seconde | Losgelaten (lang) |
| `0x06` | Aan > 2 seconden | Extra lang ingedrukt |
| `0x07` | Losgelaten | Knop is los |

**Status (Feedback):**
*   Lengte: 4 bytes (8 LEDs) of 5 bytes (16 LEDs).
*   Payload: `[01] [LEDs 0-7] [Ingangen 0-7] [Ingangen 8-15] [LEDs 8-15]`.
*   *Voorbeeld:* `01 FF 00 10 00` betekent: LEDs 0-7 aan, ingang 12 (bit 4 van de 3e byte) is actief.

**LED Aansturing:**
*   Stuur een commando met header `FE 00 21 00`, adres, en payload `(Kanaal << 4) | 2` (Aan) of `| 3` (Uit).

### 4.2. AMD (Output Module - Relais)
Relais modules hebben 8 kanalen. Ze kunnen direct of met een timer schakelen.

**Commando's:**
*   Lengte: 1 byte (direct) of 3 bytes (met timer).
*   Payload (1 byte): `(Kanaal << 5) | Functie`.
*   Payload (3 bytes): `[(Kanaal << 5) | Functie] [Tijd_lo] [Tijd_hi]`.

| Functie (Hex) | Betekenis |
| :--- | :--- |
| `0x02` | Aan |
| `0x03` | Uit |
| `0x04` | Vergrendel Aan |
| `0x05` | Vergrendel Uit |
| `0x06` | Omschakelen (Toggle) |
| `0x07` | Ontgrendel |
| `0x08` - `0x0D` | Vertraagd aan/uit, timers |

**ACK / Status:**
*   Lengte: 2 bytes.
*   Payload: `[00] [Status_Byte]`.
*   De `Status_Byte` is een bitmasker (bit 0 = kanaal 0, etc.).

### 4.3. JRM (Rolluik Module)
Rolluiken delen dezelfde adresruimte als de AMD (`0x40`), maar gebruiken een ander payload-formaat. Ze hebben 4 kanalen.

**Commando's (met tijd):**
*   Lengte: 4 bytes.
*   Payload: `[(Kanaal << 5) | Functie] [Prioriteit] [Tijd_lo] [Tijd_hi]`.
*   Kanaal: 0 t/m 3 (2 bits).
*   Tijd: 16-bit waarde in **100ms** eenheden (dus `50` = 5 seconden).

| Functie (Hex) | Betekenis |
| :--- | :--- |
| `0x02` | Stop |
| `0x03` | Omschakelen heffen stop |
| `0x04` | Omschakelen dalen stop |
| `0x05` | Heffen (Omhoog) |
| `0x06` | Senken (Omlaag) |
| `0x07` / `0x08` | Flip omhoog / omlaag |

**Feedback (JRM naar Controller):**
*   Lengte: 2 bytes.
*   `0x03` = Start met dalen
*   `0x04` = Klaar met omhoog (gestopt)
*   `0x05` = Klaar met omlaag (gestopt)
*   `0x06` = Timer gestart
*   `0x07` = Timer geannuleerd
*   `0x08` = Timer afgelopen

---

## 5. Node-RED Implementatie

De Node-RED flow (zie `flow.json`) bestaat uit:
1.  **Serial IN (bus):** Leest de RS485 dongle uit.
2.  **RS485 Master Parser:** Een functie die CRC-geleid de frames splitst, dedupliceert (tegen echo-ruis) en de status leest voor IMD, AMD en JRM.
3.  **Frame Builders (Tx):** Functies die de `C0...C1` frames bouwen voor AMD, JRM en IMD.
4.  **Serial OUT (usb):** Stuurt de frames naar de STM.

*Let op:* Het simuleren van een `Aan > 2 seconden` (Functie 6) op een IMD vereist soms dat de volledige tijdlijn (`F2 -> F4 -> F6`) naar de STM wordt gestuurd, afhankelijk van de firmware van de PHC-controller.

---

## 6. Python & Home Assistant
De opgedane kennis is direct te vertalen naar Python (voor Home Assistant integraties). De CRC-berekening en de adres-mapping (`0x40 + DIP`) zijn hierbij de sleutel tot succes.
