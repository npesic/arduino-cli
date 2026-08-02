# HIDRA — Plan & Feasibility (Phase 0)

Goal restated: **Tablet A** (USB-C host) runs an HTML5/PWA keyboard → sends key events over USB
serial → **M5StickC Plus** (ESP32) → BLE HID keyboard → **Tablet B** (BLE host).

---

## 1. Feasibility verdict

| Link in the chain | Verdict | Notes |
|---|---|---|
| ESP32 as BLE HID keyboard | ✅ Proven | Already working in `src/ino/hidra/hidra.ino` via `BleKeyboard`. |
| Serial (UART) input instead of WebSocket | ✅ Trivial | Pure firmware simplification; removes WiFi + async web server. |
| Browser → USB serial, **desktop / ChromeOS** | ✅ Solid | Web Serial API: Chrome/Edge/Opera 89+. |
| Browser → USB serial, **Android tablet** | ⚠️ Conditional | This is the only real risk. See §2. |
| Browser → USB serial, **iPad** | ❌ Not possible | Safari has no Web Serial and no WebUSB. iPad is out as Tablet A. |
| Tablet A powering the stick | ✅ | M5StickC Plus has its own LiPo, so it can run self-powered if the tablet's OTG port is stingy. |

**Overall: feasible, with one hard constraint — Tablet A must be an Android (or ChromeOS/desktop)
device running Chromium.** If Tablet A is an iPad, the whole browser-based approach dies and the
design has to change (e.g. stick exposes BLE to A as well, or a native app).

## 2. The one real risk: Web Serial on Android

- Web Serial was desktop-only for years. Chrome 148 beta (April 2026) added Android support, but
  as of now it is **Bluetooth-RFCOMM-first**, with USB serial ports arriving via the Android Serial
  API on a *limited set of devices* — not something to bet the build on.
- The reliable path on Android today is the **`web-serial-polyfill` over WebUSB**. Chrome for
  Android has supported WebUSB for a long time. The polyfill exposes the same
  `navigator.serial`-shaped API, so we write the app once against Web Serial and swap the
  implementation at runtime.
- WebUSB can only claim an interface **no kernel driver has claimed**. On stock Android there is
  usually no CH9102/CP210x/CH34x driver in the kernel, so the interface is free → claim succeeds.
  On Linux/ChromeOS the kernel *does* claim it, which is fine because there we use real Web Serial.
- The M5StickC Plus bridge chip is a **CH9102F** (CDC-ish vendor interface). Must be verified on
  real hardware — this is the first thing Phase 1 checks.

**Mitigation ladder** (stop at the first that works on the actual tablet):
1. Native Web Serial (`navigator.serial`) — free win if the device has it.
2. `web-serial-polyfill` over WebUSB — expected primary path on Android.
3. Fallback if both fail: replace the wire with **BLE from tablet A to the stick** (Web Bluetooth
   works on Android) — the stick becomes BLE-central-and-HID-peripheral. More firmware work, no USB
   cable needed. Keep this in the back pocket; do not build it up front.

## 3. Secondary gotchas worth designing around

- **DTR/RTS auto-reset.** The USB bridge's DTR/RTS lines are wired to EN/IO0 on the M5Stick. Opening
  the port with the wrong signal states reboots the ESP32 or drops it into the bootloader. The web
  app must explicitly set `dataTerminalReady:false, requestToSend:false` after open (and the WebUSB
  path must send the equivalent CH9102 control transfer).
- **Same UART is the flash/boot console.** ESP32 boot messages get dumped on the port at reset. The
  protocol must tolerate garbage before sync (use a handshake, ignore unparseable lines).
- **`BleKeyboard` vs arduino-esp32 core 3.x.** The T-vK library is happiest on core 2.x; 3.x needs a
  NimBLE-flavoured fork. Pin the core version once compilation succeeds and record it.
- **PWA needs a secure origin.** Serve it from HTTPS (GitHub Pages is enough) or `localhost`; install
  it once on tablet A, then the service worker makes it offline-capable. USB/serial permission is
  granted per-origin and typically re-prompts per session on a user gesture — the UI needs an
  explicit "Connect" button, always.
- **Toolchain is not on this machine.** No `arduino-cli`, no `~/.arduino15` here (x86_64 dev box).
  Compilation and flashing happen on the Raspberry Pi 4 as described in `PROMPT.md`.
- **Latency budget.** USB serial ~1–2 ms + BLE HID connection interval (7.5–15 ms typical) → key
  latency should land under ~30 ms. Fine for typing. Do not add artificial `delay()` in `loop()`.

## 4. Wire protocol (draft)

Line-oriented ASCII at **115200 8N1**, `\n`-terminated, so it is debuggable from a serial monitor.

| Direction | Message | Meaning |
|---|---|---|
| A→ESP | `V1\n` | Handshake / protocol version. |
| A→ESP | `D <usage> <mods>\n` | Key **down**, HID usage code + modifier bitmask (hex). |
| A→ESP | `U <usage> <mods>\n` | Key **up**. |
| A→ESP | `T <utf8 text>\n` | Type a literal string (autocomplete, paste, emoji-free ASCII). |
| A→ESP | `R\n` | Release all (panic key). |
| A→ESP | `P\n` | Ping. |
| ESP→A | `OK V1\n` | Handshake ack. |
| ESP→A | `S ble=<0\|1> batt=<pct>\n` | Status, emitted on change + every 2 s. |
| ESP→A | `!\n` | Pong. |
| ESP→A | `E <msg>\n` | Error / unparsed line. |

Sending explicit down/up (not just `write()`) is what makes real modifiers, key repeat, and
press-and-hold work — a step up from the current example, which only does `write()`.

## 5. Phases

**Phase 1 — Hardware & toolchain truth-check** (on the Pi, ~1 session)
- `lsusb` the stick → confirm CH9102F VID/PID (needed for the WebUSB filter).
- Install `esp32` core + `M5StickCPlus` + `ESP32-BLE-Keyboard`; compile the *existing* sketch
  unmodified; flash; confirm BLE pairing with tablet B still works. Record exact core/lib versions.

**Phase 2 — Firmware `hidra.ino` rewrite**
- Strip WiFi / AsyncWebServer / WebSocket. Keep M5 LCD as a status display (BLE state, last key).
- Non-blocking line reader on `Serial` (ring buffer, no `readStringUntil` blocking).
- Protocol parser → `bleKeyboard.press/release/print/releaseAll`.
- Status emitter + watchdog: if no traffic from A for N seconds, `releaseAll()` so no key sticks.
- Deliverable: types correctly on tablet B when driven by `screen`/`minicom` by hand.

**Phase 3 — Web keyboard (browser, desktop first)**
- `src/web/`: `index.html`, `app.js`, `keymap.js` (browser `KeyboardEvent.code` → HID usage),
  `transport.js` (Web Serial | WebUSB-polyfill selection behind one interface).
- On-screen key grid (touch) **and** physical-keyboard capture; sticky modifiers; connection UI.
- Validate on desktop Chrome against real hardware end-to-end.

**Phase 4 — Android + PWA**
- Wire in `web-serial-polyfill`, WebUSB device filter from Phase 1's VID/PID.
- `manifest.webmanifest` + service worker (cache-first, offline). Host on GitHub Pages.
- Test on the actual tablet A over USB-C OTG. **This phase is where the risk lands** — if WebUSB
  cannot claim the interface, escalate to mitigation ladder step 3 (§2).

**Phase 5 — Polish**
- Layout config (QWERTY/AZERTY/etc.), macros, latency measurement, LCD niceties, auto-reconnect,
  battery display, README + flashing instructions.

## 6. Proposed layout

```
hidra/
  PROMPT.md  PLAN.md
  src/ino/hidra/hidra.ino        # firmware (rewritten Phase 2)
  src/web/                       # PWA (Phase 3-4)
    index.html app.js transport.js keymap.js
    manifest.webmanifest sw.js
  docs/protocol.md               # §4, promoted once stable
```

## 7. Open questions for you

1. **What is tablet A?** (Android version / iPad / ChromeOS) — decides whether §2 risk applies at all.
2. **What is tablet B?** Only matters for BLE HID quirks (iPadOS is picky about HID report maps).
3. Is the on-screen keyboard the primary input, or should a physical BT/USB keyboard plugged into
   tablet A be relayed too?
4. Keep WiFi/WebSocket as an optional second transport, or delete it entirely? (Plan assumes delete.)

---

# Appendix A — UPDATE_1: Architecture B (BLE instead of USB serial)

Proposal: drop USB serial; tablet A talks to the stick over **Web Bluetooth**, and the stick is
simultaneously a **BLE HID keyboard** for tablet B.

## A.1 Can the ESP32 serve both tablets at once? — **Yes.**

The ESP32 is a *single BLE peripheral* holding *one GATT database* with two services, and both
tablets connect to it as centrals:

```
Tablet A ──BLE (custom control service, plaintext)──┐
                                                    ├── ESP32 (peripheral, 2 connections)
Tablet B ──BLE (HID over GATT 0x1812, bonded)───────┘
```

- **Connection count:** the ESP32 controller supports up to 9 concurrent BLE connections;
  Espressif recommends ≤3 for stability. We need 2. Comfortable.
- **Advertising:** BLE stops advertising the moment a connection is established. The firmware
  **must restart advertising in the `onConnect` callback**, otherwise the second tablet can never
  find the device. This is the single most common way this architecture "doesn't work".
- **Per-connection security:** B bonds and encrypts (HOGP requires it); A's control service is left
  unauthenticated so Web Bluetooth — which cannot drive a pairing dialog — can write to it. BLE
  security is per-connection, so mixing is legal.
- **Advertising payload:** 31 bytes won't hold flags + name + appearance + `0x1812` + a 128-bit
  custom UUID. Put HID (`0x1812` + keyboard appearance) in the ADV packet and the 128-bit control
  UUID in the **scan response**; Web Bluetooth's chooser reads scan responses.

**Control service:** use a Nordic-UART-shaped custom service (`6e400001-…`), RX characteristic
`write-without-response`, TX `notify` for status. The §4 line protocol carries over verbatim —
only the transport changes. That is the nice property of this pivot: **Phase 2's protocol and
parser are reusable, only the byte source changes.**

## A.2 Risks specific to Architecture B

1. **Web Bluetooth blocklists HID (0x1812) outright** — "direct access to HID devices like keyboards
   would let web pages become keyloggers". Tablet A therefore *cannot* touch the HID service, ever.
   Harmless here (A only uses the custom service), but it kills any simpler variant where the
   browser drives HOGP directly. It also means the same page can never be tested against the HID
   side.
2. **Tablet A must never bond with the stick in system Bluetooth settings.** If it does, Android's
   HOGP client claims the device as a physical keyboard — tablet A would then receive its own
   keystrokes, and the two stacks fight over the link. Connect *only* through the Web Bluetooth
   chooser inside the page. This deserves a warning in the UI.
3. **Library rework.** `BleKeyboard` (T-vK) assumes it owns the `BLEServer` and the advertising
   config. Adding a second service and re-advertising on connect means either reaching into its
   server object or — cleaner — moving to **NimBLE-Arduino** and building the HID service there.
   NimBLE is also markedly lighter on RAM with 2 connections. Budget real time for this.
4. **Radio contention & latency.** Two links share one radio. Give B (HID) a tight connection
   interval and A (control) a loose one, so keystroke latency lands on the link that matters.
5. **Powering the stick.** No USB cable means the M5StickC Plus runs on its ~120 mAh LiPo — that is
   roughly an hour or two. In practice it still wants a charging cable, which erodes the main
   ergonomic argument for going wireless.

## A.3 Architecture A vs B

| | A: USB serial | B: BLE control link |
|---|---|---|
| Tablet A browser needs | Web Serial *or* WebUSB | Web Bluetooth |
| Android/Fire OS support | shaky (see §2) | good on Chrome for Android |
| Cabling | USB-C OTG cable | none |
| Powers the stick | yes | no — battery only |
| Firmware complexity | low (UART reader) | medium (dual connection, re-advertise, NimBLE port) |
| Failure mode | "can't claim interface" | "second tablet can't discover" |
| iPad as tablet A | impossible | still impossible (no Web Bluetooth in Safari) |

**Recommendation: B is the better bet for a Fire tablet**, precisely because it sidesteps the
WebUSB interface-claim gamble, which is the plan's biggest unknown. Keep §4's protocol and swap
`transport.js`; that is a one-file change on the web side.

## A.4 Can tablet A be an Amazon Fire tablet? — **Probably, but only after an empirical test.**

> **RESOLVED — see Appendix B. Stock Silk supports both Web Bluetooth and WebUSB. Nothing below
> about sideloading applies; kept only as a record of what was in question.**

- Fire OS is Android-derived and Silk is Chromium-based, but **Amazon documents no support for Web
  Bluetooth, WebUSB, or Web Serial in Silk**, and Amazon strips capabilities it doesn't want.
  Treat Silk as "unknown, assume off" until measured. *(Measured: Silk 138 has both. ✅)*
- **Chrome sideloading is not a clean escape hatch:** Chrome depends on Google Play Services, so
  you must install the Play Store on Fire OS first, and that setup breaks on Fire OS updates. A
  GMS-independent Chromium build (e.g. Cromite) is the lower-friction route if Silk fails.
  *(Moot — Silk works.)*
- **Hardware is fine:** current Fire HD 8 / HD 10 / Max 11 have Bluetooth LE, and Fire HD tablets do
  support USB OTG with an adapter — so Architecture A isn't automatically dead on Fire either. The
  browser, not the hardware, is the constraint on both paths.
- Web Bluetooth on Android also requires **location permission** granted to the browser, and scanning
  fails silently-ish without it. Expect that prompt.

**The test — run this before writing any more code.** `src/web/captest.html` (added) prints the
capability table and opens each chooser. Host it on any HTTPS origin (GitHub Pages), then on the
Fire tablet:

1. Open it in **Silk** → record the table.
2. Tap "Try Bluetooth chooser" → does a device chooser appear at all?
3. If Silk shows NO across the board, sideload Cromite (or Chrome+Play) and repeat.
4. Also tap "Try USB chooser" with the M5Stick plugged in via OTG — it dumps VID/PID and attempts
   `claimInterface` on each interface, which settles §2's WebUSB question at the same time.

That one page resolves both UPDATE_1 questions and the Phase-4 risk in about fifteen minutes with
the real hardware. Send me the log output and I'll lock the architecture.

---

# Appendix B — captest results (measured) → architecture B (Web Bluetooth)

> **Superseded by Appendix C.** The measurements below stand; the *conclusion* does not. Architecture
> D (SoftAP + WebSocket) has zero open unknowns where B still has one, so D is now the build target
> and B is v2. The capability findings here remain the reason B is viable at all.

Device under test: `KFTRWI` = **Amazon Fire HD 10 (11th gen)**, Fire OS on Android 9.
Browser: **Amazon Silk 138.14.12.0.7204.244.10** — i.e. stock Silk, on Chromium 138.0.7204.244.
(The UA omits the `Silk/` token, so UA sniffing cannot detect Silk; feature-detect only.)

**This is the best possible answer to §A.4: no sideloading.** Silk ships Web Bluetooth and WebUSB
enabled, tracks Chromium closely (138 is recent), and updates through the normal Amazon channel.
The whole Play-Store-then-Chrome escape hatch, and the Cromite fallback, are off the table — drop
them from the deployment story. The PWA installs from Silk on a stock, unmodified Fire tablet.

## B.1 What the logs say

| Capability | Result | Consequence |
|---|---|---|
| Web Bluetooth | **YES — chooser opened, `gatt.connect()` returned `connected: true`** against a real ESP32 (`ESP32-WS-BLE`) | Architecture B is proven on the actual tablet. |
| WebUSB | **YES — device opened, interface 0 `CLAIMED`** | No kernel driver contest on Fire OS. §2's biggest fear is dead. |
| Web Serial | present, but `requestPort()` only offered a **Bluetooth RFCOMM/SPP** port (`…1101…`), and `open()` failed `NetworkError` | The Android build is the **RFCOMM-only** variant. Useless for USB. |
| WebHID | NO | Irrelevant. |

**Two surprises worth acting on:**

1. **The bridge chip is not a CH9102 — it is an FTDI FT232R** (`vid=0x403 pid=0x6001`,
   `Hades2001 M5stack`, interface class 255 = vendor-specific). That breaks the mitigation ladder's
   step 2: `web-serial-polyfill` hardcodes CDC-ACM (`usbControlInterfaceClass: 2`,
   `usbTransferInterfaceClass: 10`) and its `findInterface()` *throws* when no such interface
   exists. A class-255 FTDI device will never match. Architecture A would therefore need a
   hand-written FTDI-over-WebUSB driver (control requests `SET_BAUDRATE 0x03`, `SET_DATA 0x04`,
   `MODEM_CTRL 0x01`, plus stripping the 2 status bytes FTDI prepends to every IN packet). Very
   doable, but it is a whole extra component to write and debug.
2. **Web Serial on Android exists here but only over Bluetooth SPP.** That hints at an Architecture
   C — ESP32 Bluetooth Classic SPP to tablet A, BLE HID to tablet B, using the ESP32's dual-mode
   radio. Noted for completeness; **not recommended**: BR/EDR + BLE coexistence on ESP32 is
   RAM-hungry and historically flaky, and it buys nothing over B.

## B.2 Decision

**Go with Architecture B (Web Bluetooth control link).** It is the only path with a *measured*
end-to-end success on the target tablet, and it avoids writing an FTDI WebUSB driver. Architecture A
stays viable as a fallback — the interface claim works — but it now costs a custom driver, an OTG
cable, and it is unproven past the claim.

## B.3 Residual risk (the one thing captest did *not* prove)

The ESP32 that answered was a plain GATT server. **Still untested: whether Chromium on Fire OS will
connect to a peripheral that is simultaneously advertising HOGP (`0x1812`) and bonded to tablet B.**
That is Appendix A's risks #1 and #2 and it is now the top open item. Phase 1 must test it directly:
flash a stub that advertises HID + the custom service, bond it to tablet B, then run captest's
Bluetooth button on tablet A and confirm the chooser still lists it and `gatt.connect()` still
succeeds. Everything else is downstream of that answer.

## B.4 Revised phases

1. **Phase 1 (now):** dual-advertising stub on the M5Stick — HID service + custom control service,
   re-advertise in `onConnect`, HID in ADV / control UUID in scan response. Bond tablet B, then
   verify tablet A can still reach it via captest. **Go/no-go gate.**
2. **Phase 2:** NimBLE port + §4 protocol parser on the control characteristic → `press/release`.
3. **Phase 3:** the HTML5 keyboard, `transport.js` implementing the Web Bluetooth transport.
4. **Phase 4:** PWA packaging, offline service worker, install on the Fire HD 10.
5. **Phase 5:** polish (§5, unchanged).

---

# Appendix C — Architecture D: SoftAP + WebSocket (keep the WS server, drop STA mode)

Proposal: the ESP32 stops joining your WiFi and **becomes** the access point. It serves the keyboard
page and the WebSocket itself; tablet A joins that AP. The password is generated on-device and shown
on the LCD, so no credentials live in the source.

## C.1 Feasibility — **green, and it is the least risky option on the table**

- **WiFi + BLE coexistence: already proven on this exact board.** The current sketch runs WiFi STA +
  AsyncWebServer + `BleKeyboard` simultaneously on the M5StickC Plus. SoftAP uses the same radio
  coexistence machinery as STA, so this is not a new question — it is the code you already have,
  with `WiFi.begin()` swapped for `WiFi.softAP()`.
- **No exotic browser APIs.** WebSocket over `ws://` is universal. No Web Bluetooth, no WebUSB, no
  Web Serial, no polyfill, no FTDI driver.
- **BLE stays single-connection.** The ESP32 is a plain HID peripheral to tablet B, exactly as
  today. `BleKeyboard` needs no changes and **the NimBLE port is not required**.
- **Serving the page:** embed the HTML/CSS/JS in flash (LittleFS, or PROGMEM for a single-file
  build). 4 MB of flash against a keyboard page is not a constraint.

## C.2 What this kills — and it is a lot

**Architecture D removes every open risk in this document**, including the Phase-1 go/no-go gate:

| Risk | Status under D |
|---|---|
| Can Silk reach GATT while the ESP32 advertises HOGP + is bonded to B? (§B.3, the gate) | **Gone** — tablet A never touches BLE. |
| Dual BLE connection, re-advertise on connect, 31-byte ADV budget (§A.1) | **Gone** — one BLE connection. |
| NimBLE port / `BleKeyboard` owns the server (§A.2.3) | **Gone** — library used as-is. |
| Tablet A accidentally bonding as HOGP and eating its own keystrokes (§A.2.2) | **Gone.** |
| Web Bluetooth HID blocklist (§A.2.1) | Irrelevant. |
| FTDI FT232R, WebUSB claim, polyfill CDC-ACM mismatch (§B.1) | Irrelevant. |
| Tablet A must be Chromium | **Gone — iPad/Safari becomes viable as tablet A.** |

It also fixes a real security bug in the current sketch: on a shared home LAN, *anyone* who can
reach the ESP32's WebSocket can inject keystrokes into tablet B. A password-protected AP makes
keystroke injection require physical proximity plus the on-screen secret.

## C.3 What it costs

1. **Tablet A loses internet access while connected.** This is the big one. The Fire HD 10 is
   WiFi-only — no cellular fallback — so joining the stick's AP means tablet A is offline for the
   duration. Fine if tablet A is a dedicated keyboard surface; painful if it is a general-use
   tablet. **This single question should decide D vs B.**
2. **Android will fight you about the internet-less network.** Expect "This network has no internet
   access — stay connected?" and possible auto-drop. Mitigate by answering captive-portal probes
   (`/generate_204` → HTTP 204) so Fire OS marks the network as fine. Optionally hijack DNS to
   `192.168.4.1` so joining the AP pops the keyboard straight up as a captive portal.
3. **Power.** SoftAP draws roughly 120–150 mA average versus ~30–50 mA for BLE-only. Against the
   M5StickC Plus's ~120 mAh cell that is well under an hour. **D effectively requires a power
   cable** (power-only, from any charger or power bank — no data, so no FTDI concerns).
4. **Not a real PWA.** `http://192.168.4.1` is not a secure context, so no service worker and no
   proper install. In practice this barely matters — the ESP32 serves the page, so there is nothing
   to cache for offline — but "add to home screen" degrades to a plain shortcut. If you want a
   genuine installable PWA, only B delivers it.
5. **RAM and jitter.** WiFi + Bluedroid + async server together is the heaviest configuration here,
   and radio time-slicing adds some latency jitter to both links. The existing sketch shows it fits;
   there is just less headroom than under B.

## C.4 Nice things D enables

- **QR code join.** The M5 LCD library exposes `M5.Lcd.qrcode()`. Render
  `WIFI:S:HIDRA;T:WPA;P:<pass>;;` and tablet A joins by camera, no typing. Then render a second QR
  for `http://192.168.4.1/` to open the keyboard. This is a genuinely better onboarding story than
  anything B offers.
- **Rotating credentials.** Generate the passphrase at first boot, persist in NVS (`Preferences`),
  and regenerate on a long-press of Button B. Never in source control — which was the stated point.
- Works from a laptop, a phone, an iPad, anything with a browser — useful for debugging.

## C.5 Revised comparison

| | A: USB serial | B: BLE control | **D: SoftAP + WS** |
|---|---|---|---|
| Browser requirement | WebUSB + FTDI driver | Web Bluetooth (Silk ✅) | **any browser** |
| Tablet A can be an iPad | ✗ | ✗ | **✓** |
| Firmware risk | medium (new driver) | **medium-high (NimBLE, dual conn — unproven)** | **low (existing code)** |
| Open unknowns | 1 (driver) | 1 (the §B.3 gate) | **0** |
| Tablet A keeps internet | ✓ | **✓** | **✗** |
| Stick battery life | ✓ (USB-powered) | **✓ (~hours)** | ✗ (<1 h, needs cable) |
| Real installable PWA | ✓ | **✓** | ✗ |
| Cabling | data cable to tablet | **none** | power cable (any source) |
| Keystroke-injection surface | none (wired) | BLE, proximity | AP, proximity + password |

## C.6 Recommendation — **build D first, keep B as v2**

D is the fastest path to a working system and the only option with **zero open unknowns**: it is the
sketch you already have, minus the hardcoded credentials, minus the WiFi router. It is a strict
improvement on the current code, and it delivers exactly what you asked for — no password in source.

Two things make this safe rather than a detour:

- **The §4 line protocol is transport-agnostic.** The firmware parser and the web app's key handling
  are identical under D and B; only `transport.js` (WebSocket vs GATT characteristic) and the
  firmware's byte source differ. Building D does not throw away work needed for B.
- **D de-risks B.** Once D works you have a proven keyboard end-to-end, and swapping the transport
  becomes an isolated experiment you can run against the §B.3 gate without a broken system.

Switch to B if — and this is the deciding question — **tablet A needs its internet while typing**,
or if the power cable is unacceptable. If tablet A is a dedicated keyboard slab, D may simply be the
final answer.

## C.7 Revised phases (superseding §B.4)

1. **Phase 1:** `hidra.ino` → `WiFi.softAP()` with NVS-persisted random passphrase, SSID + password +
   QR on the LCD, captive-portal 204 responder, page served from flash, §4 protocol over the
   WebSocket, release-all watchdog. BLE side untouched. **This is a working system.**
   → **DONE and validated on hardware.** Both tablets connect concurrently; typing works. WiFi
   SoftAP + BLE HID coexistence on the M5StickC Plus is now measured, not assumed.
2. **Phase 2:** the real HTML5 keyboard — key grid, sticky modifiers, down/up events, physical
   keyboard capture — behind `transport.js`. → **DONE and validated on hardware.** Page is
   inlined + gzipped into the firmware by `tools/build_page.py` (14.1 kB → 4.9 kB).
3. **Phase 3 (optional, v2):** BLE transport. Run the §B.3 gate test; if it passes, add the custom
   GATT service and let the app pick its transport at runtime. **The NimBLE port is already
   largely free** — the Phase 1 build shows `ESP32-BLE-Keyboard` 0.3.2 compiling in NimBLE mode
   against NimBLE-Arduino 1.4.0, so §A.2.3's "budget real time for this" was pessimistic.
4. **Phase 4:** polish (§5).

Sources: [Chrome 148 Beta for Android adds Web Serial](https://www.notebookcheck.net/Chrome-148-Beta-for-Android-adds-Web-Serial-SharedWorker-support.1269721.0.html) ·
[PSA: Web Serial API on Android (blink-dev)](https://groups.google.com/a/chromium.org/g/blink-dev/c/yGhvQ6mEmcY) ·
[caniuse: Web Serial](https://caniuse.com/web-serial) ·
[web-serial-polyfill](https://github.com/google/web-serial-polyfill) ·
[Building a device for WebUSB](https://developer.chrome.com/docs/capabilities/build-for-webusb) ·
[Web Bluetooth GATT blocklist](https://github.com/WebBluetoothCG/registries/blob/master/gatt_blocklist.txt) ·
[ESP-IDF BLE multi-connection guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/ble/ble-multiconnection-guide.html) ·
[What is Amazon Silk](https://docs.aws.amazon.com/silk/latest/developerguide/what-is-silk.html) ·
[Installing Chrome on a Fire tablet](https://www.howtogeek.com/how-do-i-install-google-chrome-on-my-amazon-fire-tablet/) ·
[Fire HD 8 USB OTG support (XDA)](https://xdaforums.com/t/fire-hd-8-tablet-google-play-store-apps-usb-otg-support.3663114/)
