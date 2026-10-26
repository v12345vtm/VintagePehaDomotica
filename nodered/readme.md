# Peha PHC Bus Protocol & Node-RED Integration

Dit project bevat de volledige reverse-engineering van het **Peha PHC-bus protocol**, inclusief Node-RED flows voor het uitlezen en aansturen van Input (IMD), Output (AMD) en Rolluik (JRM) modules.

De communicatie verloopt via een dubbele USB-architectuur:
1. **Tx (Zenden):** Via de officiële STM-stuureenheid (`/dev/ttyACM0`). Vereist het `C0 ... C1` protocol met byte-stuffing.
2. **Rx (Ontvangen):** Via een passieve RS485-dongle op de bus (`/dev/ttyUSB0`). Levert ruwe bus-data die door een CRC-parser wordt geanalyseerd.

---

## 1. Hardware & Seriële Instellingen
*   **Baudrate:** 19200
*   **Data bits:** 8
*   **Pariteit:** None
*   **Stopbits:** 2

---

## 2. Adressering (DIP-switches)
De PHC-bus gebruikt een 8-bit adres, opgedeeld in 3 bits voor de moduleklasse en 5 bits voor de DIP-schakelaar.

| Hex Bereik | Module Type | Basis Hex |
| :--- | :--- | :--- |
| `0x00` - `0x1F` | **IMD / EMD** (Ingangen) | `0x00` |
| `0x20` - `0x3F` | MMC / IR / Busschakelaars | `0x20` |
| `0x40` - `0x5F` | **AMD** (Relais) & **JRM** (Rolluiken) | `0x40` |
| `0xA0` - `0xBF` | DIM (Dimmers) | `0xA0` |

*Formule:* `Bus_Adres = Basis_Hex + DIP_Nummer`
*(Voorbeeld: Een relais module met DIP 2 heeft adres `0x42`)*

---

## 3. Het STM-USB Protocol (Tx)

Wanneer je een commando naar de STM-stuureenheid stuurt, moet dit verpakt worden in een speciaal frame.

**Structuur:** `[C0] [Header] [Data] [CRC] [C1]`

*   **Start/Stop:** `C0` (start) en `C1` (eind).
*   **Headers:**
    *   `FE 00 06 00`: Voor Output modules (AMD/JRM) en Status-opvragen.
    *   `FE 00 21 00`: Voor Input modules (IMD) bij het simuleren van een knopdruk.
*   **Byte-Stuffing:** Als de data of CRC de bytes `C0`, `C1` of `7D` bevat, moeten deze ge-escaped worden:
    *   `C0` -> `7D E0`
    *   `C1` -> `7D E1`
    *   `7D` -> `7D 5D`

---

## 4. De RS485 Bus (Rx)

Data die van de bus komt (via de dongle) is ruw en moet geparseerd worden. 
*   **CRC Check:** CRC16/X25 (Init `0xFFFF`, Polynoom `0x8408`, XOR-out `0xFFFF`).
*   **Formaat:** `[Adres] [Toggle/Lengte] [Payload] [CRC_Lo] [CRC_Hi]`

### 4.1. IMD (Input Module)
*   **Knopdruk (Event):** Lengte 1. Payload = `(Kanaal << 4) | Functie`.
    *   `2` = Aan > 0s (Kort)
    *   `3` = Uit < 1s (Losgelaten)
    *   `4` = Aan > 1s
    *   `5` = Uit > 1s
    *   `6` = Aan > 2s
    *   `7` = Losgelaten
*   **Status (8/16 LEDs):** Lengte 4 of 5. Payload = `[01] [LEDs 0-7] [Knoppen 0-7] [Knoppen 8-15] [LEDs 8-15]`.

### 4.2. AMD (Relais)
*   **Commando:** `(Kanaal << 5) | Functie`.
    *   `0x02` = Aan, `0x03` = Uit, `0x06` = Omschakelen.
*   **ACK/Status:** Lengte 2. Payload = `[00] [Status_Byte]`.

### 4.3. JRM (Rolluik)
*   **Commando (met tijd):** Lengte 4.
    *   Payload = `[(Kanaal << 5) | Functie] [Prioriteit] [Tijd_Lo] [Tijd_Hi]`.
    *   Functies: `0x05` = Omhoog, `0x06` = Omlaag, `0x02` = Stop.
    *   Tijd is in **100ms** eenheden (dus 50 = 5 seconden).
*   **Feedback (Klaar):** Lengte 2.
    *   `0x04` = Klaar met omhoog, `0x05` = Klaar met omlaag.

---

## 5. Node-RED Implementatie

De Node-RED flow (zie `flow.json`) bestaat uit:
1.  **Serial IN (bus):** Leest de RS485 dongle uit.
2.  **RS485 Master Parser:** Een functie die CRC-geleid de frames splitst, dedupliceert (tegen echo-ruis) en de status leest.
3.  **Frame Builders (Tx):** Functies die de `C0...C1` frames bouwen voor AMD, JRM en IMD.
4.  **Serial OUT (usb):** Stuurt de frames naar de STM.

*Opmerking:* Het simuleren van een `Aan > 2 seconden` (Functie 6) op een IMD vereist mogelijk dat de volledige tijdlijn (`F2 -> F4 -> F6`) naar de STM wordt gestuurd, afhankelijk van de firmware van de PHC-controller.
