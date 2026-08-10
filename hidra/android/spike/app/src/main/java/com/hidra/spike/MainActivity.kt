package com.hidra.spike

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.bluetooth.BluetoothAdapter
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.method.ScrollingMovementMethod
import android.view.Gravity
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.GridLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * HIDRA Phase 0 spike — one screen, no keyboard layout, no styling worth the name.
 *
 * It answers exactly the five unknowns in android/PLAN.md §2 and nothing else. When a letter
 * appears on tablet B, this app has done its job and Phase 1 starts.
 *
 * Run through android/spike/README.md and paste the log into RESULTS.md.
 */
class MainActivity : Activity() {

    private lateinit var hid: HidKeyboard
    private lateinit var logView: TextView
    private lateinit var stateView: TextView
    private val ui = Handler(Looper.getMainLooper())
    private val stamp = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)
    private val lines = StringBuilder()

    private val KEY_A = 0x04
    private val SHIFT_LEFT = 0xE1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        stateView = TextView(this).apply {
            text = "idle"
            textSize = 16f
            setTypeface(Typeface.DEFAULT_BOLD)
            setPadding(24, 24, 24, 12)
            setTextColor(Color.parseColor("#3fd0a0"))
        }

        logView = TextView(this).apply {
            typeface = Typeface.MONOSPACE
            textSize = 10f
            setPadding(24, 12, 24, 24)
            setTextColor(Color.parseColor("#e9edf2"))
            movementMethod = ScrollingMovementMethod()
            setOnLongClickListener { copyLog(); true }
        }

        val grid = GridLayout(this).apply {
            columnCount = 2
            setPadding(12, 0, 12, 12)
        }
        fun button(label: String, action: () -> Unit) {
            grid.addView(Button(this).apply {
                text = label
                textSize = 12f
                setOnClickListener { action() }
            }, GridLayout.LayoutParams().apply {
                width = 0
                height = WRAP_CONTENT
                columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f)
            })
        }

        // Evidence for PLAN.md §1: confirm the BLE/HOGP route really is closed to us.
        button("0. probe HOGP") { ensurePermissions { HogpProbe(this) { m -> ui.post { log(m) } }.run() } }
        // Unknowns 1 & 2: proxy, then registerApp.
        button("1. register") { ensurePermissions { hid.start() } }
        // Unknown 3: can tablet B find and pair with us.
        button("2. discoverable") { requestDiscoverable() }
        // Then connect to the bond tablet B just made.
        button("3. connect to…") { pickHost() }
        // Unknown 4: do reports land, and do held keys behave.
        button("tap  a") { tap(KEY_A) }
        button("hold a 3s") { hold(KEY_A, 3000) }
        button("shift+a") { chord() }
        button("type hidra") { typeHidra() }
        button("release all") { hid.releaseAll(); log("manual release") }
        button("disconnect") { hid.disconnect() }
        button("unregister") { hid.stop() }
        button("copy log") { copyLog() }
        button("clear log") { lines.setLength(0); logView.text = "" }

        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#101216"))
            addView(stateView, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(grid, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(TextView(this@MainActivity).apply {
                text = "log — long-press to copy"
                textSize = 10f
                gravity = Gravity.CENTER
                setTextColor(Color.parseColor("#6c7783"))
            }, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(logView, LinearLayout.LayoutParams(MATCH_PARENT, 0).apply { weight = 1f })
        })

        hid = HidKeyboard(this) { m -> ui.post { log(m) } }
        hid.onState = { s -> ui.post { stateView.text = s } }

        log("HIDRA phase 0 spike")
        log("device: ${Build.MANUFACTURER} ${Build.MODEL}, Android ${Build.VERSION.RELEASE} " +
            "(API ${Build.VERSION.SDK_INT})")
        log("bluetooth available=${hid.bluetoothAvailable()} enabled=${hid.bluetoothEnabled()}")
        log("HID_DEVICE profile constant present: ${android.bluetooth.BluetoothProfile.HID_DEVICE}")
    }

    /**
     * Screen-off is one of the things Phase 0 is measuring, so this deliberately does NOT
     * release keys or unregister on pause — we want to see what the stack does on its own.
     * Phase 1 will release on pause (PLAN.md §2).
     */
    override fun onDestroy() {
        hid.stop()
        super.onDestroy()
    }

    // ------------------------------------------------------------------ test actions

    private fun tap(usage: Int) {
        hid.keyDown(usage)
        ui.postDelayed({ hid.keyUp(usage) }, 30)
    }

    /** Held key: tablet B should generate its own repeat, exactly as it does off the ESP32. */
    private fun hold(usage: Int, ms: Long) {
        log("holding 0x%02X for ${ms}ms — expect key repeat on the host".format(usage))
        hid.keyDown(usage)
        ui.postDelayed({ hid.keyUp(usage) }, ms)
    }

    /** Modifier + key in one report, which is what the latching UI will produce in Phase 2. */
    private fun chord() {
        hid.keyDown(SHIFT_LEFT)
        ui.postDelayed({ hid.keyDown(KEY_A) }, 20)
        ui.postDelayed({ hid.keyUp(KEY_A) }, 60)
        ui.postDelayed({ hid.keyUp(SHIFT_LEFT) }, 90)
    }

    /** Five keys in sequence — catches reports being coalesced or dropped under rate. */
    private fun typeHidra() {
        val usages = listOf(0x0B, 0x0C, 0x07, 0x15, 0x04)   // h i d r a
        var t = 0L
        for (u in usages) {
            ui.postDelayed({ hid.keyDown(u) }, t)
            ui.postDelayed({ hid.keyUp(u) }, t + 25)
            t += 60
        }
    }

    // ------------------------------------------------------------------ plumbing

    private fun pickHost() {
        val devices = hid.bondedDevices()
        if (devices.isEmpty()) {
            toast("no bonded devices — pair from tablet B first")
            return
        }
        val labels = devices.map {
            try { "${it.name}\n${it.address}" } catch (e: SecurityException) { it.address }
        }.toTypedArray()
        AlertDialog.Builder(this)
            .setTitle("Connect to host")
            .setItems(labels) { _, i -> hid.connect(devices[i]) }
            .show()
    }

    private fun requestDiscoverable() {
        startActivityForResult(
            Intent(BluetoothAdapter.ACTION_REQUEST_DISCOVERABLE)
                .putExtra(BluetoothAdapter.EXTRA_DISCOVERABLE_DURATION, 300), 2)
        log("requested 300s of discoverability — now pair from tablet B's Bluetooth settings")
    }

    /**
     * API 31+ needs BLUETOOTH_CONNECT (and ADVERTISE for discoverability) at runtime; older
     * builds have them at install time. `neverForLocation` in the manifest keeps the location
     * prompt away.
     */
    private fun ensurePermissions(then: () -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) { then(); return }
        val needed = listOf(Manifest.permission.BLUETOOTH_CONNECT,
                            Manifest.permission.BLUETOOTH_ADVERTISE)
            .filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (needed.isEmpty()) { then(); return }
        pending = then
        requestPermissions(needed.toTypedArray(), 1)
    }

    private var pending: (() -> Unit)? = null

    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, results: IntArray) {
        if (code != 1) return
        if (results.isNotEmpty() && results.all { it == PackageManager.PERMISSION_GRANTED }) {
            pending?.invoke()
        } else {
            log("FAIL: bluetooth permissions denied")
        }
        pending = null
    }

    private fun log(m: String) {
        lines.append(stamp.format(Date())).append("  ").append(m).append('\n')
        logView.text = lines
        // Keep the tail visible without wrapping the view in a ScrollView.
        val scroll = logView.layout?.getLineTop(logView.lineCount) ?: 0
        val visible = logView.height - logView.paddingTop - logView.paddingBottom
        if (scroll > visible) logView.scrollTo(0, scroll - visible)
    }

    private fun copyLog() {
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText("hidra phase 0", lines.toString()))
        toast("log copied")
    }

    private fun toast(m: String) = Toast.makeText(this, m, Toast.LENGTH_SHORT).show()
}
