package com.hidra

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReportBuilderTest {

    private val A = 0x04
    private val B = 0x05
    private val C = 0x06
    private val D = 0x07
    private val E = 0x08
    private val F = 0x09
    private val G = 0x0A
    private val SHIFT_L = 0xE1
    private val CTRL_L = 0xE0
    private val GUI_R = 0xE7

    private fun bytes(vararg v: Int) = v.map { it.toByte() }.toByteArray()

    @Test fun idleReportIsAllZeros() {
        assertArrayEquals(bytes(0, 0, 0, 0, 0, 0, 0, 0), ReportBuilder().report())
    }

    @Test fun singleKeyLandsInFirstSlot() {
        val r = ReportBuilder()
        assertTrue(r.down(A))
        assertArrayEquals(bytes(0, 0, A, 0, 0, 0, 0, 0), r.report())
    }

    /** The rule that lets keymap.js send Shift as an ordinary key event. */
    @Test fun modifiersFoldIntoTheMaskNotASlot() {
        val r = ReportBuilder()
        r.down(SHIFT_L)
        assertArrayEquals(bytes(0x02, 0, 0, 0, 0, 0, 0, 0), r.report())
        assertEquals(emptyList<Int>(), r.heldKeys)
    }

    @Test fun modifierBitsMapToTheRightPositions() {
        val r = ReportBuilder()
        r.down(CTRL_L)                                   // bit 0
        r.down(GUI_R)                                    // bit 7
        assertEquals(0x81, r.modifiers)
    }

    /** Phase 0 saw this exact report on the wire and it typed a capital A. */
    @Test fun shiftPlusKeyIsOneReport() {
        val r = ReportBuilder()
        r.down(SHIFT_L)
        r.down(A)
        assertArrayEquals(bytes(0x02, 0, A, 0, 0, 0, 0, 0), r.report())
    }

    @Test fun repeatedDownDoesNotChangeTheReport() {
        val r = ReportBuilder()
        assertTrue(r.down(A))
        assertFalse("second down should be a no-op — the host generates repeat", r.down(A))
        assertArrayEquals(bytes(0, 0, A, 0, 0, 0, 0, 0), r.report())
    }

    @Test fun repeatedModifierDownDoesNotChangeTheReport() {
        val r = ReportBuilder()
        assertTrue(r.down(SHIFT_L))
        assertFalse(r.down(SHIFT_L))
    }

    @Test fun releasingSomethingNotHeldIsHarmless() {
        val r = ReportBuilder()
        assertFalse(r.up(A))
        assertFalse(r.up(SHIFT_L))
        assertArrayEquals(bytes(0, 0, 0, 0, 0, 0, 0, 0), r.report())
    }

    @Test fun sixKeysFillAllSlots() {
        val r = ReportBuilder()
        listOf(A, B, C, D, E, F).forEach { assertTrue(r.down(it)) }
        assertArrayEquals(bytes(0, 0, A, B, C, D, E, F), r.report())
    }

    /** Rollover policy: drop the extra, never send ErrorRollOver. See ReportBuilder companion. */
    @Test fun seventhKeyIsDroppedAndDoesNotCorruptTheReport() {
        val r = ReportBuilder()
        listOf(A, B, C, D, E, F).forEach { r.down(it) }
        assertFalse(r.down(G))
        assertArrayEquals(bytes(0, 0, A, B, C, D, E, F), r.report())
    }

    @Test fun releasingDuringRolloverFreesTheSlot() {
        val r = ReportBuilder()
        listOf(A, B, C, D, E, F).forEach { r.down(it) }
        r.down(G)                                        // dropped
        assertTrue(r.up(C))
        assertTrue(r.down(G))
        assertArrayEquals(bytes(0, 0, A, B, G, D, E, F), r.report())
    }

    @Test fun freedSlotIsReusedInPlace() {
        val r = ReportBuilder()
        r.down(A); r.down(B); r.down(C)
        r.up(B)
        r.down(D)
        assertArrayEquals(bytes(0, 0, A, D, C, 0, 0, 0), r.report())
    }

    /** Modifiers must survive their key going up, or held-Shift typing breaks. */
    @Test fun keyUpLeavesModifiersHeld() {
        val r = ReportBuilder()
        r.down(SHIFT_L); r.down(A); r.up(A)
        assertArrayEquals(bytes(0x02, 0, 0, 0, 0, 0, 0, 0), r.report())
    }

    @Test fun releaseAllClearsEverything() {
        val r = ReportBuilder()
        r.down(SHIFT_L); r.down(CTRL_L); r.down(A); r.down(B)
        assertTrue(r.releaseAll())
        assertArrayEquals(bytes(0, 0, 0, 0, 0, 0, 0, 0), r.report())
        assertTrue(r.isIdle)
    }

    @Test fun releaseAllOnAnIdleBuilderChangesNothing() {
        assertFalse(ReportBuilder().releaseAll())
    }

    @Test fun invalidUsagesAreIgnored() {
        val r = ReportBuilder()
        assertFalse(r.down(0))
        assertFalse(r.down(-1))
        assertFalse(r.down(0x100))
        assertTrue(r.isIdle)
    }

    /** The report handed out must not alias internal state. */
    @Test fun reportIsACopy() {
        val r = ReportBuilder()
        r.down(A)
        val first = r.report()
        r.up(A)
        assertArrayEquals(bytes(0, 0, A, 0, 0, 0, 0, 0), first)
    }

    /** End to end: the "hidra" sequence the spike typed, one key at a time. */
    @Test fun typingASequenceLeavesNothingHeld() {
        val r = ReportBuilder()
        for (u in listOf(0x0B, 0x0C, 0x07, 0x15, 0x04)) {
            assertTrue(r.down(u))
            assertTrue(r.up(u))
        }
        assertTrue(r.isIdle)
    }
}
