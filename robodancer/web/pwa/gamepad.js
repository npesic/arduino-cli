// Gamepad polling and mixing preview.
//
// The drone is authoritative -- it runs the same mixing in mixing.py. This
// mirrors it only to drive the HUD without waiting for a round trip, and to
// decide whether anything changed enough to be worth sending. The thresholds
// come from /api/status so the two can never drift apart.

export const DEFAULT_TUNING = {
  drive_deadzone: 0.15,
  spin_speed: 0.8,
  invert_steering: false,
  pantilt_deadzone: 0.12,
  deadman_timeout: 0.4,
  axes: { lx: 0, ly: 1, rx: 2, ry: 3 },
  buttons: { up: 12, down: 13, left: 14, right: 15 },
};

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Mirrors mixing.stick_mix().
export function stickMix(x, y, t) {
  const speed = -y;
  if (Math.abs(speed) < t.drive_deadzone) return [0, 0];
  let ax = clamp(x, -1, 1);
  if (Math.abs(ax) < t.drive_deadzone) ax = 0;
  if (t.invert_steering) ax = -ax;
  return [
    clamp(speed * (ax <= 0 ? 1 : 1 - ax), -1, 1),
    clamp(speed * (ax >= 0 ? 1 : 1 + ax), -1, 1),
  ];
}

// Mirrors mixing.dpad_mix(): opposing presses cancel.
export function dpadMix(pressed, t) {
  const has = (i) => pressed.includes(i);
  let up = has(t.buttons.up), down = has(t.buttons.down);
  let left = has(t.buttons.left), right = has(t.buttons.right);
  if (up && down) up = down = false;
  if (left && right) left = right = false;
  const s = t.spin_speed;
  if (left) return [-s, s];
  if (right) return [s, -s];
  if (up) return [s, s];
  if (down) return [-s, -s];
  return null;
}

export function mix(axes, pressed, t) {
  const spin = dpadMix(pressed, t);
  if (spin) return spin;
  if (axes.length <= Math.max(t.axes.lx, t.axes.ly)) return [0, 0];
  return stickMix(axes[t.axes.lx], axes[t.axes.ly], t);
}

// Right stick, in PanTilt's convention: +pan aims right, +tilt aims up.
export function look(axes, t) {
  if (axes.length <= Math.max(t.axes.rx, t.axes.ry)) return [0, 0];
  return [axes[t.axes.rx], -axes[t.axes.ry]];
}

export function readPad() {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  for (const pad of pads) {
    if (pad) {
      return {
        id: pad.id,
        axes: Array.from(pad.axes, (v) => Math.round(v * 1000) / 1000),
        buttons: pad.buttons.reduce(
          (acc, b, i) => (b.pressed ? (acc.push(i), acc) : acc), []),
      };
    }
  }
  return null;
}

// True when the sample differs enough to be worth a message.
export function changed(a, b, epsilon = 0.02) {
  if (!a || !b) return true;
  if (a.buttons.length !== b.buttons.length) return true;
  if (a.buttons.some((v, i) => v !== b.buttons[i])) return true;
  if (a.axes.length !== b.axes.length) return true;
  return a.axes.some((v, i) => Math.abs(v - b.axes[i]) > epsilon);
}
