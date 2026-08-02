# HIDRA

BLE HID keyboard bridge on an M5StickC Plus.

**Tablet A** joins the stick's own WiFi access point and opens a keyboard page served from the
stick. **Tablet B** is paired to the stick over Bluetooth as an ordinary BLE keyboard. Keystrokes
made on A land on B.

No WiFi credentials in source: the passphrase is generated on first boot, stored in NVS, and shown
on the LCD as text and as a scannable QR code.

See [`PLAN.md`](PLAN.md) for the architecture comparison and feasibility work (this is
"Architecture D", Appendix C).

## Status

**Phase 1 — working on hardware.** Validated on an M5StickC Plus with an Amazon Fire HD 10 as
tablet A: both tablets connect simultaneously and keystrokes reach tablet B.

**Phase 2 — working on hardware.** Full QWERTY touch keyboard in `src/web/`: latching modifiers,
multi-touch chords, shifted legends, physical-keyboard capture, auto-reconnect. Renders on the
Fire HD 10 and types on tablet B.

The system is usable end to end. What remains is polish (PLAN.md §5) and the optional BLE
transport (§C.7 phase 3).

## Dependencies

Board: `esp32:esp32:m5stick-c`. Libraries:

| Library | Notes |
|---|---|
| `M5StickCPlus` | LCD, buttons, AXP192 battery |
| `ESP32-BLE-Keyboard` (T-vK) | install from the [release ZIP](https://github.com/T-vK/ESP32-BLE-Keyboard/releases); not in the library index |
| `ESPAsyncWebServer` | |
| `AsyncTCP` | required by ESPAsyncWebServer |

`DNSServer` and `Preferences` ship with the ESP32 core.

> Pin the ESP32 core to a **2.x** release. `ESP32-BLE-Keyboard` does not build against core 3.x
> without a NimBLE-flavoured fork.

```bash
arduino-cli core install esp32:esp32
arduino-cli lib install M5StickCPlus ESPAsyncWebServer AsyncTCP
# ESP32-BLE-Keyboard: unzip into ~/Arduino/libraries/
```

## Build and flash

```bash
python3 tools/build_page.py          # only after editing src/web/
./arduino-cli compile --fqbn esp32:esp32:m5stick-c -e src/ino/hidra
esptool.py --port /dev/ttyUSB0 write_flash 0x10000 \
    src/ino/hidra/build/esp32.esp32.m5stick-c/hidra.ino.bin
```

The keyboard lives in `src/web/` as ordinary HTML/CSS/JS. `tools/build_page.py` inlines it into a
single gzipped blob and writes `src/ino/hidra/page.h`, which the firmware serves with
`Content-Encoding: gzip`. **`page.h` is generated — edit `src/web/`, never the header.** The
generated file is committed, so a plain compile works without running Python.

To preview the layout without flashing, open `src/web/index.html` straight from disk; it renders
and reports `preview (no device)` instead of trying to connect.

### Verified build

Phase 1 compiles clean on the Raspberry Pi 4 with:

| Component | Version |
|---|---|
| `esp32:esp32` core | **1.0.6** |
| M5StickC-Plus | 0.0.8 |
| ESP32-BLE-Keyboard | 0.3.2 — **NimBLE mode** (pulls NimBLE-Arduino 1.4.0) |
| ESPAsyncWebServer | 1.2.3 |

Footprint: **flash 1050194 / 1310720 (80%)**, RAM 49236 bytes global, 278444 free.

Two notes for later:

- **Flash is at 80%** on the default partition scheme, and the Phase 2 keyboard page will be
  considerably larger than the Phase 1 test page. The stick has 4 MB, so switch partition schemes
  before that becomes a problem — list the options with
  `arduino-cli board details --fqbn esp32:esp32:m5stick-c` and append e.g.
  `:PartitionScheme=huge_app` to the FQBN.
- **BleKeyboard is already building against NimBLE**, not Bluedroid. That is a happy accident worth
  keeping: NimBLE is the stack Phase 3 (BLE transport, PLAN.md §C.7) needs for the dual-connection
  work, so that port is partly done already.

## Use

1. Power the stick. **Keep it on a charger** — SoftAP + BLE drains the ~120 mAh cell in well
   under an hour.
2. **Tablet B:** pair with `HIDRA` in Bluetooth settings. The LCD shows `BLE: paired`.
3. **Tablet A:** scan the first QR (or join WiFi `HIDRA` with the passphrase on screen).
4. Press button A to show the second QR, or just open `http://192.168.4.1/`.
5. Type. Keys go to tablet B.

Button A cycles the three screens (join / open page / status). **Holding button B for 1.5 s
regenerates the passphrase** and reboots.

Tablet A has no internet while joined to this AP — it is a closed network with no uplink. The
firmware answers Android's connectivity probes with `204` so Fire OS does not nag about it or
silently drop the network.

## Protocol

Newline-terminated ASCII over the WebSocket at `/ws`. Transport-agnostic by design — Phase 3 can
swap the WebSocket for a BLE GATT characteristic without touching the parser or the key handling.

| Direction | Message | Meaning |
|---|---|---|
| A→ESP | `V1` | handshake |
| A→ESP | `D <usage> <mods>` | key down, HID usage id (decimal) |
| A→ESP | `U <usage> <mods>` | key up |
| A→ESP | `T <text>` | type a literal string |
| A→ESP | `R` | release everything |
| A→ESP | `P` | ping |
| ESP→A | `OK V1` | handshake ack |
| ESP→A | `S ble=<0\|1> batt=<pct>` | status, every 2 s |
| ESP→A | `!` | pong |
| ESP→A | `E <msg>` | parse error |

Usages `0xE0`–`0xE7` are the modifier keys and maintain the modifier bitmask themselves, so a
client can send them as ordinary key events. The `<mods>` field is honoured only when `<usage>`
is `0` — `D 0 <mods>` sets the modifier state outright.

Sending explicit down/up rather than `write()` is what makes held modifiers, key repeat, and
press-and-hold work. Up to six non-modifier keys may be held at once (standard 6KRO).

If the client goes quiet for 3 s with keys still down, the firmware releases everything — otherwise
a dropped connection leaves tablet B with a wedged modifier and an infinite key repeat. A
WebSocket disconnect releases immediately.

## Security

The AP is WPA2 with a device-generated passphrase, so injecting keystrokes into tablet B requires
physical proximity plus the secret on the screen. Anyone who does join the AP can type into tablet
B — treat the passphrase as the only thing standing between a bystander and your other tablet, and
regenerate it (button B) if it has been on screen in public.
