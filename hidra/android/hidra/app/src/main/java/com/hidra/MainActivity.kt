package com.hidra

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.view.WindowManager
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import java.io.IOException

/**
 * The keyboard. `src/web/` rendered in a WebView, typing over BLE.
 *
 * The layout, the latching modifiers, the multi-touch chords and the shifted legends are the
 * PWA's — the same files the ESP32 serves, copied into assets at build time and not forked.
 * Only `transport.js` differs: the Android one bridges to [KeyTransport] instead of opening a
 * WebSocket. That is the whole of Phase 2.
 *
 * Assets are served from a synthetic `https://hidra.local/` origin rather than
 * `file:///android_asset/`, because app.js treats an empty `location.host` as "no device, render
 * a preview" — which is exactly right when you open the page from disk, and exactly wrong here.
 */
class MainActivity : Activity() {

    private lateinit var link: HogpTransport
    private lateinit var web: WebView
    private val main = Handler(Looper.getMainLooper())

    private var pageReady = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // A keyboard the user is looking at must not sleep under them.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        goImmersive()

        link = HogpTransport(this)
        link.onLog = { m -> Log.i(TAG, m) }
        link.onStatus = { s -> main.post { pushStatus(s) } }

        web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.setSupportZoom(false)
            settings.builtInZoomControls = false
            // The layout sizes itself from the viewport; a system font scale of 1.3 would push
            // key legends out of their keys.
            settings.textZoom = 100
            overScrollMode = View.OVER_SCROLL_NEVER
            isVerticalScrollBarEnabled = false
            isHorizontalScrollBarEnabled = false
            webViewClient = AssetClient()
            addJavascriptInterface(Bridge(), "HidraNative")
        }
        if (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) {
            WebView.setWebContentsDebuggingEnabled(true)
        }
        setContentView(web)

        web.loadUrl("https://$ASSET_HOST/index.html")

        withPermissions { link.start() }
    }

    /**
     * Backgrounding stops our events but not the far end's key repeat, so let go of everything
     * first. The link itself stays up.
     */
    override fun onPause() {
        link.releaseAll()
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        goImmersive()
        pushStatus(link.status)
    }

    override fun onDestroy() {
        link.stop()
        web.destroy()
        super.onDestroy()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) goImmersive()
    }

    @Suppress("DEPRECATION")
    private fun goImmersive() {
        window.decorView.systemUiVisibility =
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
    }

    // ------------------------------------------------------------------ page → keys

    /**
     * app.js speaks the same newline protocol it speaks to the firmware. Both ends are in one
     * process now, but keeping the wire format means app.js is byte-identical across the two
     * builds — which is the point of the exercise.
     *
     * JavaScript bridge calls arrive on a binder thread; the transport expects the main thread.
     */
    private inner class Bridge {
        @JavascriptInterface
        fun ready() {
            main.post {
                pageReady = true
                pushStatus(link.status)
                Log.i(TAG, "keyboard page ready")
            }
        }

        @JavascriptInterface
        fun send(line: String) {
            main.post { handle(line) }
        }
    }

    private fun handle(line: String) {
        val parts = line.trim().split(' ')
        when (parts.firstOrNull()) {
            "D" -> parts.getOrNull(1)?.toIntOrNull()?.let { link.keyDown(it) }
            "U" -> parts.getOrNull(1)?.toIntOrNull()?.let { link.keyUp(it) }
            "R" -> link.releaseAll()
            "P" -> Unit                       // app.js keeps the firmware's watchdog fed
            else -> Log.w(TAG, "unhandled line from the page: $line")
        }
    }

    // ------------------------------------------------------------------ keys → page

    /**
     * Drives the status pills app.js already knows how to render: the `ws` pill and the
     * greyed-out veil follow "can I type right now", the `ble` pill follows whether a device is
     * connected at all, and the battery is the phone's.
     */
    private fun pushStatus(s: LinkStatus) {
        if (!pageReady) return
        js("window.HIDRA_ANDROID.status(${s.canType})")
        val connected = if (link.currentHost != null) 1 else 0
        js("window.HIDRA_ANDROID.line('S ble=$connected batt=${link.batteryPercent()}')")
    }

    private fun js(code: String) = web.evaluateJavascript(code, null)

    // ------------------------------------------------------------------ assets

    /**
     * Serves `src/web/` from a made-up origin. Nothing leaves the device — requests are
     * answered from assets before any network is touched.
     */
    private inner class AssetClient : WebViewClient() {
        override fun shouldInterceptRequest(
            view: WebView, request: WebResourceRequest
        ): WebResourceResponse? {
            val url: Uri = request.url
            if (!url.host.equals(ASSET_HOST, ignoreCase = true)) return null
            val path = url.path?.trimStart('/')?.ifEmpty { "index.html" } ?: "index.html"
            return try {
                WebResourceResponse(mimeOf(path), "utf-8", assets.open(path))
            } catch (e: IOException) {
                Log.w(TAG, "no such asset: $path")
                null
            }
        }
    }

    private fun mimeOf(path: String) = when {
        path.endsWith(".html") -> "text/html"
        path.endsWith(".css") -> "text/css"
        path.endsWith(".js") -> "application/javascript"
        else -> "application/octet-stream"
    }

    // ------------------------------------------------------------------ permissions

    /** Runtime BLUETOOTH_CONNECT/ADVERTISE on Android 12+; install-time below that. */
    private fun withPermissions(then: () -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) { then(); return }
        val missing = listOf(Manifest.permission.BLUETOOTH_CONNECT,
                             Manifest.permission.BLUETOOTH_ADVERTISE)
            .filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isEmpty()) { then(); return }
        pending = then
        requestPermissions(missing.toTypedArray(), REQ_PERMISSIONS)
    }

    private var pending: (() -> Unit)? = null

    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, results: IntArray) {
        if (code != REQ_PERMISSIONS) return
        if (results.isNotEmpty() && results.all { it == PackageManager.PERMISSION_GRANTED }) {
            pending?.invoke()
        } else {
            Log.e(TAG, "Bluetooth permission denied — HIDRA cannot be a keyboard without it")
        }
        pending = null
    }

    companion object {
        private const val TAG = "HIDRA"
        private const val ASSET_HOST = "hidra.local"
        private const val REQ_PERMISSIONS = 1
    }
}
