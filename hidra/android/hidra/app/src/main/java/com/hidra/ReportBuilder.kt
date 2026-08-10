package com.hidra

/**
 * The 8-byte HID boot keyboard report: `[modifiers, reserved, k1..k6]`.
 *
 * Deliberately free of Android imports so it runs on the JVM under unit test — this is the one
 * piece of HIDRA with logic subtle enough to get quietly wrong, and a wrong report is invisible
 * until someone notices a stuck key on a device across the room.
 *
 * The semantics mirror the ESP32 firmware exactly, so `src/web/keymap.js` usage ids work here
 * unchanged and tablet B cannot tell the two implementations apart.
 */
class ReportBuilder {

    private var mods = 0
    private val slots = IntArray(SLOTS)

    /** Bitmask of held modifiers, bit 0 = LeftCtrl … bit 7 = RightGUI. */
    val modifiers get() = mods

    /** Held non-modifier usages, in slot order, zeros omitted. */
    val heldKeys get() = slots.filter { it != 0 }

    val isIdle get() = mods == 0 && slots.all { it == 0 }

    /**
     * Presses a usage. Returns whether the report changed — callers use that to skip sending a
     * report identical to the last one.
     *
     * Usages 0xE0–0xE7 fold into the modifier byte instead of consuming a key slot. That is
     * what lets a client treat Shift as an ordinary key event and still get a real held
     * modifier on the far end.
     */
    fun down(usage: Int): Boolean {
        if (!valid(usage)) return false
        if (isModifier(usage)) {
            val bit = 1 shl (usage - MOD_FIRST)
            if (mods and bit != 0) return false
            mods = mods or bit
            return true
        }
        if (slots.contains(usage)) return false          // already down; auto-repeat is the host's job
        val free = slots.indexOf(0)
        if (free < 0) return false                       // see rollover note below
        slots[free] = usage
        return true
    }

    /** Releases a usage. Releasing something that is not held is a no-op, not an error. */
    fun up(usage: Int): Boolean {
        if (!valid(usage)) return false
        if (isModifier(usage)) {
            val bit = 1 shl (usage - MOD_FIRST)
            if (mods and bit == 0) return false
            mods = mods and bit.inv()
            return true
        }
        val at = slots.indexOf(usage)
        if (at < 0) return false
        slots[at] = 0
        return true
    }

    /** Everything up. The report that unwedges a stuck modifier on the far end. */
    fun releaseAll(): Boolean {
        if (isIdle) return false
        mods = 0
        slots.fill(0)
        return true
    }

    /** A fresh copy each time — the caller hands this to the Bluetooth stack. */
    fun report() = byteArrayOf(
        mods.toByte(), 0,
        slots[0].toByte(), slots[1].toByte(), slots[2].toByte(),
        slots[3].toByte(), slots[4].toByte(), slots[5].toByte()
    )

    private fun valid(usage: Int) = usage in 1..0xFF
    private fun isModifier(usage: Int) = usage in MOD_FIRST..MOD_LAST

    companion object {
        const val SLOTS = 6
        const val MOD_FIRST = 0xE0
        const val MOD_LAST = 0xE7

        /**
         * Rollover: a seventh simultaneous non-modifier key is dropped rather than sending the
         * spec's ErrorRollOver report (all six slots set to 0x01). Two reasons. The firmware
         * already behaves this way, so the two implementations stay identical; and on a touch
         * keyboard six simultaneous non-modifier keys means a palm on the glass, where dropping
         * the extra is far kinder than telling the host every key is invalid.
         */
        const val ROLLOVER_POLICY = "drop extras, no ErrorRollOver"
    }
}
