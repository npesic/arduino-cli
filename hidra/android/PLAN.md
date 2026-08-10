# HIDRA Android — Plan & Feasibility (Phase 0)

Goal: drop the M5StickC Plus. The Pixel *is* the keyboard. Tablet B pairs with the phone
directly and sees an ordinary Bluetooth keyboard; the on-screen layout is the one from
`src/web/`, which already looks and feels right.

```
  today:   [tablet A] --WiFi/WS--> [M5StickC] --BLE HID--> [tablet B]
  android: [Pixel]    ------------ Bluetooth HID --------> [tablet B]
```

Everything between the two boxes disappears: no AP, no passphrase, no QR codes, no battery
budget, no 80%-full flash, no `page.h` build step, no watchdog for a dropped WiFi link.

---

## 1. Feasibility verdict — green, with one correction to the brief

**Android can act as a HID keyboard for another device — measured, not assumed.** The API is
`BluetoothHidDevice` (`BluetoothProfile.HID_DEVICE`, API 28+ / Android 9). The app registers an
SDP record with a HID report descriptor, tablet B pairs with the phone as a keyboard, and the
app pushes 8-byte boot-keyboard reports with `sendReport()`. Phase 0 ran this end to end on a
Pixel 2 XL / Android 11: proxy, registration, pairing, connection, and correct reports on the
wire. See [`spike/RESULTS.md`](spike/RESULTS.md).

This is *classic* Bluetooth HID (HIDP over L2CAP), not BLE / HOGP. So the name "HID keyboard
over BLE" is inaccurate for the Android build, and idle power is slightly higher than a BLE
peripheral would draw — irrelevant on a phone battery.

**Correction to an earlier claim in this document.** This section previously said a
non-privileged app *cannot* register the HID service UUID `0x1812` on a GATT server, and that
HOGP was therefore closed. Phase 0's probe disproves it: `addService(0x1812)` **succeeded**,
status 0, on Android 11. The restriction I was thinking of is on the GATT *client* side —
Android stops apps reading HID characteristics of a remote device, to prevent keylogging — and
I wrongly generalised it to the server side.

What that does *not* establish is that HOGP works end to end. A functioning BLE keyboard needs
the full service (report map, protocol mode, HID control point, report characteristics with
CCCDs and report-reference descriptors), advertising with the keyboard appearance, a bond, and
a host willing to accept it. `addService` succeeding proves only that the first door opens.
**BLE HID is therefore open-but-unproven, not closed.** Since classic HID already works, the
plan below still builds on classic; §5 adds an optional Phase 0b to settle HOGP if BLE
specifically matters to you.

### What carries over unchanged

| Asset | Reuse |
|---|---|
| `src/web/keymap.js` | verbatim — HID usage ids are the same numbers `sendReport` wants |
| `src/web/style.css` | verbatim |
| `src/web/app.js` | all of it except `transport.js` (latch/one-shot/multi-touch logic is sound) |
| Report shape | firmware's 6KRO model = the boot keyboard descriptor, 1:1 |
| `src/web/transport.js` | **dies** — replaced by a JS↔Kotlin bridge or by native calls |

The wire protocol in `README.md` also dies. There is no wire. `D 4 0` becomes a direct call
into the HID stack in the same process.

---

## 2. The one real risk: the HID Device role on a Pixel

Everything else is ordinary app work. This is the item that decides whether the project
exists, so it gets tested first and alone.

Specific unknowns, in the order they can bite:

1. **`getProfileProxy(HID_DEVICE)` returns a proxy** on the Pixel's Android build. Some OEM
   builds ship with the HID device role disabled; stock Pixel should be fine.
2. **`registerApp()` succeeds** and the phone starts advertising an SDP HID record. Requires
   `BLUETOOTH_CONNECT` at runtime (API 31+) and, for the pairing step, discoverability.
3. **Fire HD 10 pairs with it.** Fire OS is Android 9 with Amazon's Bluetooth settings UI; it
   pairs with BT keyboards routinely, but it must *offer* the phone as a pairable input
   device rather than trying the phone-to-phone (OPP/PAN) flow.
4. **Reports actually land** and held keys/modifiers behave — tablet B does its own key
   repeat off the held report, as it does today with the ESP32.
5. **Reconnect after sleep.** Phone screen off → link drops → does it come back on wake, or
   does it need re-pairing? This is the classic sore spot for HID-device apps.

Mitigation if (1) or (2) fails on the target Pixel: fall back to keeping the M5StickC as the
bridge and making the Android app a native client of the existing WebSocket protocol. That is
a strictly worse product but salvages the UI work, so **structure the code so the UI never
knows which transport it is on** (§4).

### Secondary gotchas worth designing around now

- **Gesture navigation eats the edge keys.** On a Pixel with gesture nav, back-swipes from
  the left and right edges will fire instead of `esc`/`Backspace`/arrows. Needs
  `View.setSystemGestureExclusionRects()` (capped at 200 dp per edge by the OS) plus immersive
  mode. Plan for it; do not discover it at demo time.
- **Screen must stay on.** `FLAG_KEEP_SCREEN_ON` while the keyboard is foreground.
- **Backgrounding must release everything.** Same reason as the PWA's `visibilitychange`
  handler: a held modifier plus a lost foreground leaves tablet B with an infinite repeat.
  Release all on `onPause`.
- **Landscape.** A phone in portrait cannot show a usable QWERTY row. Lock landscape, or
  offer a compact portrait layout as a later nicety.
- **Foreground service** if the link must survive the app leaving the foreground. Probably
  not wanted for v1 — see Open Questions.
- **Android 12+ permissions**: `BLUETOOTH_CONNECT` and `BLUETOOTH_ADVERTISE` at runtime, with
  the `neverForLocation` flavour so no location prompt appears.

---

## 3. UI: reuse the WebView, don't rewrite it yet

Two options, and I recommend the first for the milestone that has to look right.

**A. WebView hosting `src/web/` (recommended for v1).** The HTML/CSS/JS goes into
`assets/`, loaded from `file:///android_asset/`. `transport.js` is replaced by a
`@JavascriptInterface` bridge object that exposes `down(usage)`, `up(usage)`, `releaseAll()`.
Visual fidelity is not "close to" the PWA — it *is* the PWA. Multi-touch pointer events work
in a WebView; `touch-action: none` and `user-select: none` already handle the browser's
gesture stealing. Cost: ~20 lines of glue. Latency added by the bridge hop is well under a
millisecond and invisible next to the ~10 ms Bluetooth transit.

**B. Native Jetpack Compose keyboard.** Better long-term home for haptics, key preview
pop-ups, predictive text, per-key long-press alternates, and the Play Store review. Costs a
full reimplementation of `app.js`'s latch state machine and `style.css`'s proportional row
layout, and it will not match pixel-for-pixel on the first try.

Do A now, keep B as a later phase once the layout stops changing. The bridge interface is the
same either way, so B is a UI swap and not a rewrite of anything else.

---

## 4. Architecture

```
  ┌──────────────── KeyboardActivity (landscape, immersive, keep-screen-on) ───┐
  │                                                                            │
  │   WebView ──assets/{index,keymap,style}──►  the PWA layout, unchanged      │
  │      │                                                                     │
  │      │ @JavascriptInterface  down(usage) / up(usage) / releaseAll()        │
  │      ▼                                                                     │
  │   KeyTransport  (interface)                                                │
  │      ├── HogpTransport     → BLE GATT notify on 0x2A4D         [primary]   │
  │      │     └── advertises 0x1812; re-advertises after a disconnect         │
  │      └── HidTransport      → BluetoothHidDevice.sendReport()   [fallback]  │
  │            └── kept, unused: covers hosts that do classic but not BLE      │
  │      ▼                                                                     │
  │   ReportBuilder — modifier bitmask + 6 keycode slots, boot protocol        │
  └────────────────────────────────────────────────────────────────────────────┘
```

`ReportBuilder` is the only piece with real logic worth unit-testing: the 8-byte report
(`[mods, 0, k1..k6]`), usages `0xE0`–`0xE7` folding into the modifier byte rather than a key
slot, rollover behaviour when a 7th key goes down. That mirrors what the firmware does today,
so the semantics are already specified and already proven against tablet B.

---

## 5. Phases

**Phase 0 — spike (the feasibility check the brief asks for).** *Done — passed on a Pixel 2 XL /
Android 11; see [`spike/RESULTS.md`](spike/RESULTS.md). Outstanding: T4 (reconnect after
screen-off / host sleep) and, if the target is a newer Pixel, the API 31+ permission path.*
One activity, buttons, no layout. Tap → send `a`
down, 30 ms later `a` up. Success = the letter appears in a text field on the Fire HD 10 after
pairing from its Bluetooth settings. Also measure: time from tap to character, behaviour after
screen-off/on, behaviour after tablet B sleeps. The spike also probes `addService(0x1812)` so
§1's HOGP claim is evidenced rather than asserted.
*Exit criteria: a character lands, and reconnect after sleep is characterised (working, or
working-with-a-tap, or broken).* Protocol in `spike/README.md`, results into
`spike/RESULTS.md`.

**Phase 0b — HOGP.** *Done — passed on hardware 2026-08-10; see [`spike-hogp/`](spike-hogp/).
BLE is a working transport, and the route past the Chromebook's classic-Bluetooth filter.*
Promoted from optional to necessary by the Chromebook finding above: classic Bluetooth cannot
present the phone as a keyboard, and a BLE peripheral is classified from an advertisement the
app controls. Full HID-over-GATT service on top of the `addService` Phase 0 showed is permitted
— report map, HID info, protocol mode, control point, input/output reports with CCCDs and
report-reference descriptors — plus Device Info and Battery, advertising service UUID `0x1812`.
Timeboxed: if no host accepts it, classic HID still works everywhere except the Chromebook.

**Phase 1 — transport.** *Done — see [`hidra/`](hidra/). Builds; 18 unit tests green; not yet
run on hardware.* `KeyTransport` + `HidTransport` + `ReportBuilder`, held-key set, release-all,
connection state as an observable. Pairing/connection UI: list bonded HID hosts, connect, show
status. Unit tests on `ReportBuilder`.

*Carried from Phase 0:* registration is not permanent — the spike lost it after ~5 minutes and
then failed every `connect()` silently (RESULTS.md §T1b). `HidTransport` must treat
`onAppStatusChanged(registered=false)` as recoverable and re-register, and the UI must never
offer a connect button that quietly does nothing.

**Phase 1b — switch the app to BLE.** *Done — see [`hidra/`](hidra/). Builds; 18 tests green;
not yet run on hardware.* Phase 0b passed on *both* the Chromebook and the Fire HD
10, while classic reaches only the Fire. BLE is therefore a superset across everything in scope,
and the app consolidates on it rather than carrying two transports and a picker.

Port `HogpPeripheral` into `hidra/` as `HogpTransport : KeyTransport` and make it the transport
`MainActivity` uses. Nothing above the interface changes. Then close the gaps the spike left
(spike-hogp/RESULTS.md): re-advertise after a disconnect, release-all on pause, reconnect to a
bonded host, real battery level.

`HidTransport` stays in the tree, unused. It is written, works, and costs nothing behind the
interface — cheap insurance for a host that speaks classic but not BLE. Delete it if that never
materialises.

**Phase 2 — the keyboard.** *Done — see [`hidra/`](hidra/). Builds; not yet run on hardware.*
`src/web/` into assets, `transport.js` swapped for the bridge, WebView wired to `KeyTransport`.
At this point it is the PWA, minus the ESP32. Status pills in the existing top bar are
repointed at the Bluetooth connection state; the battery pill shows the phone's battery.

The four shared files are copied from `src/web/` by a Gradle task rather than duplicated, so
there is no fork to keep in step — verified by editing `src/web/app.js` and finding the change
in the APK. Landscape lock, keep-screen-on and immersive mode came along early, because without
them the keyboard is not testable as a keyboard; the rest of Phase 3 still stands.

**Phase 3 — Android polish.** Landscape lock, immersive mode, gesture exclusion rects,
keep-screen-on, release-all on pause, haptic feedback per key, auto-reconnect to the last
host, optional foreground service.

**Phase 4 — optional.** Native Compose layout (§3B). Mouse/trackpad HID reports (a second
report id in the same descriptor — genuinely useful on a tablet). Text macros. Capture of a
physical keyboard plugged into the phone. Consumer-control keys (volume, media).

Phases 0–2 are the working product. 3 is what makes it pleasant. 4 is appetite.

---

## 6. Target matrix (decided 2026-08-10)

**Sending side: any Pixel phone, Pixel 2 XL first.** So the app spans **API 28 (Android 9)
through API 35+**, and both permission models are live: install-time on the Pixel 2 XL (API 30,
its ceiling) and runtime `BLUETOOTH_CONNECT` on anything Android 12 or newer. Phase 0 only
exercised the install-time path — the runtime path is written but unproven, and it gates the
app starting at all, so it is the first thing to test on a modern Pixel.

Gesture navigation also only matters on the newer phones; the Pixel 2 XL predates it.

**Receiving side: anything that accepts a Bluetooth keyboard** — the Fire HD 10, a Chromebook
tablet, a laptop, another phone. This is the strongest argument yet for the choices already
made:

- **Classic HID over HOGP.** Every desktop and mobile OS has accepted classic Bluetooth
  keyboards for twenty years; BLE/HOGP support is more variable and more recent. Phase 0b drops
  to the bottom of the list — it would *narrow* compatibility, not widen it.
- **Boot-protocol descriptor.** The most universally understood keyboard there is. Keep it, and
  keep honouring `onGetReport` and `onSetProtocol`, because unfamiliar hosts do probe.
- **No assumptions about the pairing UI.** Fire OS, ChromeOS and Windows all drive pairing
  differently. The app's job is to be registered and discoverable; the host's job is the rest.

Per-device testing is then a matrix, not a checklist. Suggested minimum before calling it done:
{Pixel 2 XL, one current Pixel} × {Fire HD 10, Chromebook tablet}.

### Resolved: the Chromebook does not list the phone over classic Bluetooth (2026-08-10)

**Fixed by moving to BLE.** Phase 0b advertises `0x1812` and the Chromebook lists, bonds and
types — as does the Fire HD 10. The investigation below is kept because it is the reason the
architecture changed, and because it is the argument against ever going back to classic.


Phase 1 on a Pixel 2 XL types to the Fire HD 10, but the Chromebook tablet never shows the
phone in its Bluetooth pairing list.

**Confirmed:** `chrome://bluetooth-internals` on the Chromebook *does* list the Pixel during a
scan. So the Chromebook sees it and the Settings UI filters it out — a display problem, not a
discovery or discoverability one. Work on the advertising side cannot fix it.

Two candidate causes remain. **(a) Class of Device** — read the Class column in
bluetooth-internals to confirm. **(b) Phone Hub / Connected Devices** — if the Chromebook and
the phone share a Google account, ChromeOS may route the phone there and keep it out of the
Bluetooth list; check Settings → Connected devices. (b) is worth ruling out first because it
explains something (a) does not: ChromeOS lists phones happily for audio and tethering, so it
plainly does not filter phones categorically.

For (a), the hypothesis is **Class of Device**. The adapter advertises major class *Phone*;
registering a HID device app does not change that, and Android gives apps no way to set it (it
comes from a system property). Fire OS lists everything discoverable and so is unaffected;
ChromeOS filters its available-devices list by device type, so a phone offering a keyboard is
filtered out.

Nothing requires the receiving device to *see* the phone — only that the two are bonded, and
either side can start that. **Bond from the phone** (Settings → Connected devices → Pair new
device, with the Chromebook's pairing dialog open), then use HIDRA's connect list as normal.

That workaround is also the diagnostic:

- **Works** → the problem is only ChromeOS's discovery filter. Fix is an in-app pairing flow
  that scans and calls `createBond()` from the phone, rather than relying on the receiving
  device to list us. Worth building, given "any receiving device".
- **Fails** → ChromeOS is refusing HID connections from a phone-class device outright. Much
  more serious, and the one scenario that would make Phase 0b (HOGP) worth revisiting, since a
  BLE peripheral advertises its own appearance independent of the adapter's CoD.

### Consequence for the keyboard layout — worth deciding early

The PWA layout in `src/web/` was drawn for a 10-inch tablet. The Pixel 2 XL is a 5.7-inch
screen; in landscape, a full 15-column QWERTY plus a function row gives roughly **7 mm keys** —
below the ~9 mm that touch targets want, and the function row makes it worse. The layout cannot
simply be ported at full width to the smallest supported phone.

Options, cheapest first: drop the function row to a toggle rather than an always-on row (it is
already reference material more than a typing target, per `style.css`); scale key height by
screen size; or ship a compact layout for phones under ~6 inches and the full one above. I would
do the first two in Phase 2 and only build a second layout if it still feels cramped.

## 7. Still open

1. **Should the phone stay usable while HIDRA is connected** (foreground service, keyboard in
   a floating window or notification) — or is full-screen-or-nothing fine for v1? Full-screen
   is much simpler and I'd start there.
4. **Does this repo hold the Android app, or a new one?** An Android Gradle project under
   `android/` sits oddly beside an Arduino sketch tree, but keeping the keymap in one place is
   worth a lot. I'd keep it here and let the build tooling ignore what it doesn't own.
5. **Play Store, or sideload?** Store distribution adds a privacy policy and a data-safety
   declaration for the Bluetooth usage; sideload adds nothing.

---

## 8. Where this stands

Phase 0 is **done and passed** — characters confirmed on the receiving device, reports
byte-correct, one defect found (registration expiry, RESULTS.md §T1b) and one plan claim
corrected (HOGP is not blocked). Phase 1 can start.

Two things are still owed from hardware, neither of which blocks Phase 1:

- **T4** — reconnect after screen-off / host sleep / backgrounding. The last real risk. Its
  result tunes the auto-reconnect work rather than deciding whether to do it.
- **API 31+ startup** — permissions and registration on a current Pixel.
