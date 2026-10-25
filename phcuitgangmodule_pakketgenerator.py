"""
amd_frame_generator.py — genereer alle AMD-frames voor een gegeven adres.

Elk commando wordt in TWEE varianten getoond:
  - toggle=0
  - toggle=1

Status-opvraag gebruikt payload 01 (zoals bevestigd).
"""

import sys


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


def hexstr(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def build_frame(addr: int, toggle: bool, payload: bytes) -> bytes:
    length = len(payload)
    b1 = (0x80 if toggle else 0x00) | length
    body = bytes([addr, b1]) + payload
    crc = phc_crc(body)
    return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


FUNCTIES = [
    (0x02, "Ein",                  False),
    (0x03, "Aus",                  False),
    (0x04, "An Lock",              False),
    (0x05, "Aus Lock",             False),
    (0x06, "Umschalten",           False),
    (0x07, "Unlock",               False),
    (0x08, "An verzögert",         True),
    (0x09, "Aus verzögert",        True),
    (0x0A, "An mit Timer",         True),
    (0x0B, "Aus mit Timer",        True),
    (0x0C, "Umschalten verzögert", True),
    (0x0D, "Umschalten mit Timer", True),
]


def print_beide_varianten(addr: int, naam: str, payload: bytes):
    """Print één commando in beide toggle-varianten, naast elkaar."""
    f0 = build_frame(addr, False, payload)
    f1 = build_frame(addr, True, payload)
    print(f"  {naam:<26} {hexstr(f0):<22} | {hexstr(f1)}")


def genereer(addr: int, channels=range(8), tijden=(10, 30, 100)):
    dip = addr & 0x1F
    device = addr & 0xE0

    print()
    print("=" * 90)
    print(f"  AMD frame-generator   addr=0x{addr:02X}   DIP={dip}   device=0x{device:02X}")
    print("=" * 90)
    print(f"  {'Commando':<26} {'toggle=0':<22} | {'toggle=1'}")
    print("-" * 90)

    # -- Algemene commando's --
    print("--- ALGEMEEN ---")
    print_beide_varianten(addr, "Config (broadcast stop)",
                          bytes([0xFE, 0x00, 0xFF]))
    print_beide_varianten(addr, "Status opvragen",
                          bytes([0x01]))           # <-- payload 01
    print()

    # -- Per kanaal --
    for ch in channels:
        print(f"--- KANAAL {ch} ---")

        for functie, naam, heeft_tijd in FUNCTIES:
            if not heeft_tijd:
                payload = bytes([(ch << 5) | functie])
                print_beide_varianten(addr, naam, payload)
            else:
                for sec in tijden:
                    tijd = int(sec * 10)
                    payload = bytes([
                        (ch << 5) | functie,
                        tijd & 0xFF,
                        (tijd >> 8) & 0xFF,
                    ])
                    label = f"{naam} ({sec}s)"
                    print_beide_varianten(addr, label, payload)
        print()

    print("=" * 90)
    print("  Klaar. Kopieer een regel naar je RS485-terminal.")
    print("=" * 90)


def main():
    print("=" * 90)
    print("  AMD frame-generator")
    print("=" * 90)
    print("  Voer een adres in (hex, bv. 50). Typ 'q' om te stoppen.")
    print()

    while True:
        try:
            invoer = input("Adres> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not invoer or invoer.lower() == "q":
            break

        try:
            addr = int(invoer, 16)
        except ValueError:
            print(f"[!] Ongeldig hex-adres: {invoer}")
            continue

        if not 0 <= addr <= 0xFF:
            print("[!] Adres moet 0x00..0xFF zijn")
            continue

        genereer(addr)
        print()


if __name__ == "__main__":
    main()