# HIDRA for Android

The phone is the keyboard. Pair it with a tablet, a Chromebook, a laptop — anything that
accepts a Bluetooth keyboard — and type on the phone to type on that device. No ESP32.

Feasibility, architecture and phasing live in [`../PLAN.md`](../PLAN.md). The Phase 0 spike that
proved it works on hardware is in [`../spike/`](../spike/); this is the real app.

## Status — Phase 2

The keyboard works: the PWA layout, rendered in a WebView, typing over BLE.

| File | Role |
|---|---|
| `ReportBuilder.kt` | the 8-byte boot report; modifier folding, 6KRO, rollover. Pure Kotlin, unit-tested |
| `KeyTransport.kt` | what the UI is allowed to know: down/up/releaseAll and a link state |
| `HogpTransport.kt` | **the transport** — BLE HID-over-GATT: services, advertising, notify |
| `HidTransport.kt` | classic Bluetooth HID. Unused; kept as fallback, see below |
| `MainActivity.kt` | the WebView, the JS bridge, and the asset server |
| `assets/transport.js` | the only part of the page that is Android's own |

## The keyboard is not a fork of the PWA

`index.html`, `style.css`, `keymap.js` and `app.js` are copied out of `src/web/` **at build
time** by the `syncKeyboard` Gradle task — the same files the ESP32 firmware serves. Edit
`src/web/`, rebuild, and the change is in both products. There is no second copy to keep in
step, and `app.js` is byte-identical in the APK and in `page.h`.

Only `transport.js` differs. The Android one lives in `app/src/main/assets/`, declares the same
`WebSocketTransport` class name that `app.js` constructs, and bridges to `KeyTransport` instead
of opening a socket. It shadows the web one by simply not being copied over.

The page is served from a synthetic `https://hidra.local/` origin rather than
`file:///android_asset/`, because `app.js` reads an empty `location.host` as "no device, render
a preview" — right when you open the page from disk, wrong here. Requests are answered from
assets and never touch the network.

Two Android-only touches live in `assets/transport.js`, so `src/web/` never learns which host it
is on: the offline veil says *waiting for a device* rather than *reconnecting*, and the function
row folds away on short screens with a toggle in the status bar. That last one matters — a full
15-column layout with a function row on a 5.7-inch Pixel 2 XL gives roughly 7 mm keys.

## Why BLE and not classic Bluetooth

Both work. Classic only reaches *some* devices:

| | Fire HD 10 | Chromebook tablet |
|---|---|---|
| Classic HID | works | **never appears in the pairing list** |
| BLE HOGP | works | works |

The Chromebook filters the phone out because Class of Device and a dozen phone profiles
classify it as a phone, and no app can change that — `setBluetoothClass()` is a privileged
system API. A BLE peripheral is classified from an advertisement the app *does* control, so
HIDRA advertises service UUID `0x1812` and is taken for a keyboard. Full story in
[`../PLAN.md`](../PLAN.md) §6 and [`../spike-hogp/RESULTS.md`](../spike-hogp/RESULTS.md).

`HidTransport` stays in the tree, unused, as insurance for a host that speaks classic but not
BLE. Delete it if that never turns up.

## There is no connect button

Over BLE the phone is the peripheral. It advertises; the other device connects to it from its
own Bluetooth settings, exactly as it would to any keyboard. HIDRA cannot dial out — what it
does instead is keep advertising and re-offer itself to the device that connected last.

## What this does that the spikes did not

- **Re-advertises after a disconnect**, so a host that sleeps or wanders out of range can come
  back without the app being restarted. The HOGP spike stopped dead.
- **Distinguishes connected from usable.** A device can be connected and still not have
  subscribed to the input report, in which case nothing types. That is its own link state, and
  the keys stay disabled until the host actually accepts the keyboard.
- **Releases every key on `onPause`** — a held modifier plus a backgrounded app leaves the
  receiving device with a stuck Shift and infinite repeat.
- **Reports the phone's real battery** to the host, which shows it as the keyboard's battery.
  The spike hardcoded 100%.

## Build

Toolchain: SDK 35 at `~/android-sdk`, Gradle wrapper in the project, JDK 17. On a fresh clone:

```bash
echo "sdk.dir=$HOME/android-sdk" > local.properties
./gradlew test assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

18 unit tests cover `ReportBuilder`. They are worth keeping honest — a wrong report byte is
invisible until someone notices a stuck key on a device across the room.

## Use

1. Open HIDRA and grant the Bluetooth permission. It locks to landscape and keeps the screen on.
2. On the *other* device, open Bluetooth settings and connect to the phone. It advertises
   under the phone's own Bluetooth name, not "HIDRA" — see PLAN.md §6.
3. The status line turns green once that device accepts the keyboard. Type.

It re-advertises after a disconnect and re-offers itself to the last device used, so waking
the other device should be enough to get typing again. **forget device** clears that memory.

## Supported devices

Any Pixel from Android 9 (API 28) upward, provided it can advertise as a BLE peripheral.
Validated on a Pixel 2 XL / Android 11. The runtime-permission path used by Android 12+ is
implemented but not yet exercised on hardware.

Receiving side: anything that accepts a Bluetooth keyboard. Validated on the Fire HD 10 and a
Chromebook tablet. The report map is the HID 1.11 boot keyboard, which is the most widely
understood keyboard there is.
