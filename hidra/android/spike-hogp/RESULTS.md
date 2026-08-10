# Phase 0b results

| | |
|---|---|
| Date | 2026-08-10 |
| Phone | Google Pixel 2 XL, Android 11 (API 30) |
| Receiving devices | Chromebook tablet, Fire HD 10 |

## Outcome — pass, on both hosts

- [x] **T0b-1** Advertising started; all three services registered
- [x] **T0b-2** **The Chromebook lists the phone** — the thing classic Bluetooth could not achieve
- [x] **T0b-3** Bonded and subscribed to the input report
- [x] **T0b-4** Typing works
- [x] **T0b-5** **The Fire HD 10 also works over BLE**
- [ ] **T0b-6** Reconnect after screen-off — not recorded

**Verdict: BLE/HOGP works on every device tested, and is the only transport that does.**

Not captured from the run: how ChromeOS labelled the device in its pairing list, the individual
typing sub-tests, and reconnect behaviour. Worth filling in from a log if one is kept, but none
of it changes the architectural conclusion.

## Why this settles the transport question

| | Fire HD 10 | Chromebook tablet |
|---|---|---|
| Classic HID (Phase 0/1) | works | **not listed** — filtered as a phone |
| BLE HOGP (Phase 0b) | works | works |

BLE is a superset of what classic achieves across the devices in scope, so the app consolidates
on one transport instead of carrying two and asking the user to choose. See PLAN.md §4.

## What the spike does not yet do

Carried into the port (PLAN.md Phase 1b):

- **No re-advertising after a disconnect.** The spike stops advertising once a host connects and
  does not resume when it drops, so recovery needs a manual stop/advertise. BLE reconnect is
  historically fussier than classic; this is the first thing to get right.
- **No release-all on pause.** Same stuck-modifier risk the classic build already handles.
- **No bonded-device awareness.** It advertises and waits; it cannot reconnect to a known host.
- **Battery level is hardcoded to 100%.** Real battery is a one-liner and a nice touch on a
  device the host thinks is a keyboard.
