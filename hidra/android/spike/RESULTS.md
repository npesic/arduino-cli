# Phase 0 results

Source log: [`../spike.log`](../spike.log), run 09:12–09:25.

| | |
|---|---|
| Date | 2026-08-10 |
| Phone | Google Pixel 2 XL, Android 11 (API 30) |
| Host used | `Peripheral MK` / A8:E6:21:EC:A7:95 |

## Outcome

- [x] **T0** HOGP probe — **inverted result**: `addService(0x1812)` *succeeded*
- [x] **T1** HID_DEVICE proxy obtained, `registerApp()` succeeded
- [x] **T2** Host paired and connected
- [x] **T3** Characters appeared on the receiving device — **exit criterion met**
- [ ] **T4** Reconnect behaviour — **not run**
- [ ] **T5** Latency — **not recorded**

**Verdict: pass on the core hypothesis.** The Bluetooth HID device role works on this phone: it
registered, a host connected, and every report was accepted. One new defect found (§T1b) and one
plan claim disproved (§T0).

## T0 — HOGP probe: the plan was wrong

```
09:12:16.485  addService() returned true
09:12:16.489  *** addService(0x1812) SUCCEEDED ***
```

PLAN.md §1 claimed a non-privileged app cannot register the HID service UUID on a GATT server.
It can, at least on Android 11. That claim is now corrected in the plan.

This does **not** mean BLE HID works — `addService` is the first step of many (full HOGP service,
advertising with keyboard appearance, bonding, a willing host). It means the route is
**open-but-unproven** rather than closed, which is a different thing and a better position for
the original brief. Optional Phase 0b in PLAN.md §5 settles it if wanted.

## T1 — registration: works

```
09:12:19.653  got HID_DEVICE proxy
09:12:19.659  registerApp() accepted
09:12:19.663  onAppStatusChanged: registered=true
```

Clean, ~30 ms end to end. The kill-switch unknown is cleared.

Note the API level: **30**, so the API 31+ runtime-permission path never ran. If the target phone
is a newer Pixel, that path is still untested — the only untested thing left in T1.

## T1b — the app gets silently deregistered *(new, not predicted)*

```
09:12:19.663  onAppStatusChanged: registered=true
09:17:36.100  onAppStatusChanged: registered=false plugged=null    ← nobody asked for this
09:22:50.135  connect(Peripheral MK/…) -> false                    ← fails, no registration
09:23:04.387  registerApp() accepted                               ← manual recovery
09:24:14.967  connect(Peripheral MK/…) -> true                     ← now it works
```

Registration dropped on its own after ~5m16s, and every later `connect()` failed silently until
the app was re-registered by hand. Without the log this looks like "the connect button is
broken".

Two candidate causes, neither confirmed:

1. **Discoverability window.** The first 300 s window opened at 09:12:34 and would expire at
   09:17:34 — two seconds before the deregistration. Tight correlation. But a second window was
   requested at 09:16:47, which should have extended it, so either that request was declined or
   the two are unrelated.
2. **Backgrounding.** The phone was in Bluetooth settings for much of that stretch. But it stayed
   registered for five minutes of that, so a simple foreground rule does not fit either.

**Phase 1 requirement regardless of cause:** treat `onAppStatusChanged(registered=false)` as a
recoverable event and re-register automatically, rather than assuming registration is permanent.
This is exactly the kind of thing the spike existed to find.

## T2 — pairing: works

Host connected on the second attempt, once registration was restored:

```
09:24:14.974  -> connecting
09:24:15.550  -> CONNECTED        (576 ms)
```

Not recorded: how the host described the phone in its chooser, and whether a PIN was needed.

## T3 — reports: all correct on the wire

Every report matches what the descriptor promises. Spot-checking the bytes:

| Action | Report | Correct? |
|---|---|---|
| `a` down | `00 00 04 00 00 00 00 00` | yes — usage 0x04 in slot 1 |
| shift down | `02 00 00 00 00 00 00 00` | yes — 0x02 is bit 1, Left Shift |
| shift+`a` | `02 00 04 00 00 00 00 00` | yes — modifier and key in one report |
| `hidra` | `0B, 0C, 07, 15, 04` | yes — h i d r a |
| release all | `00 00 00 00 00 00 00 00` | yes |

The modifier-folding rule (`0xE0`–`0xE7` → bitmask, everything else → key slot) behaves exactly
as the ESP32 firmware does, so `keymap.js` will drop straight in.

`sendReport()` local call time: **691 µs – 2.6 ms**, one outlier at **7.5 ms** on the key-up after
the 3-second hold. That is the local call only, not air time.

**Confirmed by eye:** characters appeared on the receiving device. Phase 0's exit criterion is
met.

## T4 / T5 — not run

No screen-off, host-sleep, backgrounding, or out-of-range cycles in the log, and no latency
impression. T4 is the sore spot the plan flagged and the last real risk before Phase 1.

## What changes in the plan

1. §1's HOGP claim corrected; BLE reclassified open-but-unproven.
2. New Phase 1 requirement: auto-re-register on `registered=false` (T1b).
3. Still to do: T4, and T1 on an API 31+ phone if the target is a newer Pixel.
