// HID usage tables and the physical key layout.
// Usage ids are USB HID Keyboard/Keypad page (0x07) — the same numbers the firmware puts
// straight into the report, so nothing here needs to know about ASCII.

const HIDRA_KEYMAP = (() => {
  const U = {
    Enter: 0x28, Escape: 0x29, Backspace: 0x2A, Tab: 0x2B, Space: 0x2C,
    Minus: 0x2D, Equal: 0x2E, BracketLeft: 0x2F, BracketRight: 0x30, Backslash: 0x31,
    Semicolon: 0x33, Quote: 0x34, Backquote: 0x35, Comma: 0x36, Period: 0x37, Slash: 0x38,
    CapsLock: 0x39,
    PrintScreen: 0x46, ScrollLock: 0x47, Pause: 0x48,
    Insert: 0x49, Home: 0x4A, PageUp: 0x4B, Delete: 0x4C, End: 0x4D, PageDown: 0x4E,
    ArrowRight: 0x4F, ArrowLeft: 0x50, ArrowDown: 0x51, ArrowUp: 0x52,
    ContextMenu: 0x65,
    ControlLeft: 0xE0, ShiftLeft: 0xE1, AltLeft: 0xE2, MetaLeft: 0xE3,
    ControlRight: 0xE4, ShiftRight: 0xE5, AltRight: 0xE6, MetaRight: 0xE7,
  };
  for (let i = 0; i < 26; i++) U['Key' + String.fromCharCode(65 + i)] = 0x04 + i;
  for (let i = 1; i <= 9; i++) U['Digit' + i] = 0x1D + i;
  U.Digit0 = 0x27;
  for (let i = 1; i <= 12; i++) U['F' + i] = 0x39 + i;

  const MODIFIERS = new Set(['ControlLeft', 'ShiftLeft', 'AltLeft', 'MetaLeft',
                             'ControlRight', 'ShiftRight', 'AltRight', 'MetaRight']);

  // Layout rows. Each key: [code, label, shiftedLabel, widthUnits].
  // Width units are relative; a row is laid out proportionally, so they need not sum to a
  // fixed total — but keeping rows near 15 units keeps the columns visually aligned.
  const k = (code, label, shifted, w) => ({ code, label, shifted: shifted || null, w: w || 1 });

  const FN_ROW = [
    k('Escape', 'esc', null, 1.2),
    ...Array.from({ length: 12 }, (_, i) => k('F' + (i + 1), 'F' + (i + 1))),
    k('Delete', 'del', null, 1.3),
    k('Home', 'home', null, 1.3),
    k('End', 'end', null, 1.3),
  ];

  const MAIN_ROWS = [
    [
      k('Backquote', '`', '~'), k('Digit1', '1', '!'), k('Digit2', '2', '@'),
      k('Digit3', '3', '#'), k('Digit4', '4', '$'), k('Digit5', '5', '%'),
      k('Digit6', '6', '^'), k('Digit7', '7', '&'), k('Digit8', '8', '*'),
      k('Digit9', '9', '('), k('Digit0', '0', ')'), k('Minus', '-', '_'),
      k('Equal', '=', '+'), k('Backspace', '⌫', null, 2),
    ],
    [
      k('Tab', 'tab', null, 1.5),
      k('KeyQ', 'q', 'Q'), k('KeyW', 'w', 'W'), k('KeyE', 'e', 'E'), k('KeyR', 'r', 'R'),
      k('KeyT', 't', 'T'), k('KeyY', 'y', 'Y'), k('KeyU', 'u', 'U'), k('KeyI', 'i', 'I'),
      k('KeyO', 'o', 'O'), k('KeyP', 'p', 'P'),
      k('BracketLeft', '[', '{'), k('BracketRight', ']', '}'),
      k('Backslash', '\\', '|', 1.5),
    ],
    [
      k('CapsLock', 'caps', null, 1.8),
      k('KeyA', 'a', 'A'), k('KeyS', 's', 'S'), k('KeyD', 'd', 'D'), k('KeyF', 'f', 'F'),
      k('KeyG', 'g', 'G'), k('KeyH', 'h', 'H'), k('KeyJ', 'j', 'J'), k('KeyK', 'k', 'K'),
      k('KeyL', 'l', 'L'),
      k('Semicolon', ';', ':'), k('Quote', '\'', '"'),
      k('Enter', '⏎', null, 2.2),
    ],
    [
      k('ShiftLeft', 'shift', null, 2.3),
      k('KeyZ', 'z', 'Z'), k('KeyX', 'x', 'X'), k('KeyC', 'c', 'C'), k('KeyV', 'v', 'V'),
      k('KeyB', 'b', 'B'), k('KeyN', 'n', 'N'), k('KeyM', 'm', 'M'),
      k('Comma', ',', '<'), k('Period', '.', '>'), k('Slash', '/', '?'),
      k('ShiftRight', 'shift', null, 1.7),
      k('ArrowUp', '▲', null, 1),
      k('Delete', 'del', null, 1),
    ],
    [
      k('ControlLeft', 'ctrl', null, 1.5),
      k('MetaLeft', 'win', null, 1.2),
      k('AltLeft', 'alt', null, 1.2),
      k('Space', '', null, 6),
      k('AltRight', 'alt', null, 1.2),
      k('ControlRight', 'ctrl', null, 1.5),
      k('ArrowLeft', '◀', null, 1),
      k('ArrowDown', '▼', null, 1),
      k('ArrowRight', '▶', null, 1),
    ],
  ];

  return { U, MODIFIERS, FN_ROW, MAIN_ROWS };
})();
