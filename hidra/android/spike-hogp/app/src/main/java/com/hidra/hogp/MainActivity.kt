package com.hidra.hogp

import android.Manifest
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
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
 * Phase 0b spike. Same shape as the Phase 0 app: buttons and a log, no keyboard.
 *
 * The question it answers is narrow — does a receiving device that refuses to list the phone
 * over classic Bluetooth list it as an input device over BLE, and does it type?
 *
 * Protocol in README.md; results into RESULTS.md.
 */
class MainActivity : Activity() {

    private lateinit var hogp: HogpPeripheral
    private lateinit var stateView: TextView
    private lateinit var logView: TextView
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

        button("1. advertise") { ensurePermissions { hogp.start() } }
        button("tap  a") { tap(KEY_A) }
        button("hold a 3s") { hold(KEY_A, 3000) }
        button("shift+a") { chord() }
        button("type hidra") { typeHidra() }
        button("release all") { hogp.releaseAll() }
        button("stop") { hogp.stop() }
        button("copy log") { copyLog() }

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

        hogp = HogpPeripheral(this) { m -> ui.post { log(m) } }
        hogp.onState = { s -> ui.post { stateView.text = s } }

        log("HIDRA phase 0b — HID over GATT")
        log("device: ${Build.MANUFACTURER} ${Build.MODEL}, Android ${Build.VERSION.RELEASE} " +
            "(API ${Build.VERSION.SDK_INT})")
        log("BLE peripheral mode supported: " +
            packageManager.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE))
    }

    override fun onDestroy() {
        hogp.stop()
        super.onDestroy()
    }

    // ------------------------------------------------------------------ test actions

    private fun tap(usage: Int) {
        hogp.keyDown(usage)
        ui.postDelayed({ hogp.keyUp(usage) }, 30)
    }

    private fun hold(usage: Int, ms: Long) {
        log("holding 0x%02X for ${ms}ms — expect key repeat on the host".format(usage))
        hogp.keyDown(usage)
        ui.postDelayed({ hogp.keyUp(usage) }, ms)
    }

    private fun chord() {
        hogp.keyDown(SHIFT_LEFT)
        ui.postDelayed({ hogp.keyDown(KEY_A) }, 20)
        ui.postDelayed({ hogp.keyUp(KEY_A) }, 60)
        ui.postDelayed({ hogp.keyUp(SHIFT_LEFT) }, 90)
    }

    private fun typeHidra() {
        var t = 0L
        for (u in listOf(0x0B, 0x0C, 0x07, 0x15, 0x04)) {      // h i d r a
            ui.postDelayed({ hogp.keyDown(u) }, t)
            ui.postDelayed({ hogp.keyUp(u) }, t + 25)
            t += 60
        }
    }

    // ------------------------------------------------------------------ plumbing

    /** BLE advertising needs BLUETOOTH_ADVERTISE on API 31+; below that it is install-time. */
    private fun ensurePermissions(then: () -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) { then(); return }
        val needed = listOf(Manifest.permission.BLUETOOTH_ADVERTISE,
                            Manifest.permission.BLUETOOTH_CONNECT)
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
            log("FAIL: Bluetooth permissions denied")
        }
        pending = null
    }

    private fun log(m: String) {
        lines.append(stamp.format(Date())).append("  ").append(m).append('\n')
        logView.text = lines
        val bottom = logView.layout?.getLineTop(logView.lineCount) ?: 0
        val visible = logView.height - logView.paddingTop - logView.paddingBottom
        if (bottom > visible) logView.scrollTo(0, bottom - visible)
    }

    private fun copyLog() {
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText("hidra phase 0b", lines.toString()))
        Toast.makeText(this, "log copied", Toast.LENGTH_SHORT).show()
    }
}
