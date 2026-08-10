package com.hidra

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHidDevice
import android.bluetooth.BluetoothHidDeviceAppSdpSettings
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.os.Handler
import android.os.Looper
import java.util.concurrent.Executors

/**
 * Keys out over classic Bluetooth HID, using the boot-protocol keyboard descriptor that Phase 0
 * proved on hardware.
 *
 * The design difference from the spike is that this one **assumes registration is temporary**.
 * Phase 0 lost its registration after five minutes with no warning, after which every connect
 * attempt failed silently (spike/RESULTS.md §T1b). So `registered=false` is treated as an
 * ordinary recoverable event with backoff, not as an error, and the state is published so the
 * UI can grey out controls that would not work.
 *
 * Permission note: callers must hold BLUETOOTH_CONNECT (runtime on API 31+, install-time
 * below) before calling [start]. MainActivity gates on that.
 */
@SuppressLint("MissingPermission")
class HidTransport(context: Context) : KeyTransport {

    private val app = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor()
    private val report = ReportBuilder()

    private val adapter: BluetoothAdapter? =
        (app.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager?)?.adapter

    private var proxy: BluetoothHidDevice? = null
    private var host: BluetoothDevice? = null

    /** True between start() and stop(); the switch that tells recovery whether to bother. */
    private var running = false
    private var retryDelay = FIRST_RETRY_MS

    override var status = LinkStatus(LinkState.STOPPED); private set
    override var onStatus: ((LinkStatus) -> Unit)? = null
    override var onLog: ((String) -> Unit)? = null

    /** Last device we were connected to, so the UI can offer it first. Phase 3 auto-connects. */
    var lastHostAddress: String? = null
        private set

    // ------------------------------------------------------------------ lifecycle

    override fun start() {
        if (running) return
        running = true
        retryDelay = FIRST_RETRY_MS
        when {
            adapter == null -> fail("this device has no Bluetooth adapter")
            !adapter.isEnabled -> fail("Bluetooth is off")
            else -> acquireProxy()
        }
    }

    override fun stop() {
        running = false
        main.removeCallbacksAndMessages(null)
        releaseAll()
        proxy?.let {
            it.unregisterApp()
            adapter?.closeProfileProxy(BluetoothProfile.HID_DEVICE, it)
        }
        proxy = null
        host = null
        publish(LinkStatus(LinkState.STOPPED))
    }

    private fun acquireProxy() {
        val a = adapter ?: return
        publish(LinkStatus(LinkState.STARTING, detail = "getting HID profile…"))
        if (!a.getProfileProxy(app, serviceListener, BluetoothProfile.HID_DEVICE)) {
            // The kill switch from PLAN.md §2. Unrecoverable: this build has no HID device role.
            fail("this phone does not support the Bluetooth HID device role")
        }
    }

    private val serviceListener = object : BluetoothProfile.ServiceListener {
        override fun onServiceConnected(profile: Int, p: BluetoothProfile) {
            if (profile != BluetoothProfile.HID_DEVICE) return
            proxy = p as BluetoothHidDevice
            log("HID profile proxy acquired")
            register()
        }

        override fun onServiceDisconnected(profile: Int) {
            if (profile != BluetoothProfile.HID_DEVICE) return
            log("HID profile proxy lost")
            proxy = null
            host = null
            scheduleRecovery("profile proxy lost")
        }
    }

    private fun register() {
        val p = proxy ?: return scheduleRecovery("no proxy")
        publish(LinkStatus(LinkState.STARTING, detail = "registering keyboard…"))
        if (!p.registerApp(SDP, null, null, executor, callback)) {
            scheduleRecovery("registerApp() refused")
        }
    }

    /**
     * The Phase 0 defect, handled. Backs off so a persistently unhappy stack does not become a
     * busy loop, and gives up loudly rather than pretending to work.
     */
    private fun scheduleRecovery(why: String) {
        if (!running) return
        if (retryDelay > MAX_RETRY_MS) {
            fail("could not register as a keyboard ($why)")
            return
        }
        val delay = retryDelay
        retryDelay *= 2
        log("recovering in ${delay}ms: $why")
        publish(LinkStatus(LinkState.STARTING, detail = "reconnecting… ($why)"))
        main.postDelayed({
            if (!running) return@postDelayed
            if (proxy == null) acquireProxy() else register()
        }, delay)
    }

    private val callback = object : BluetoothHidDevice.Callback() {

        override fun onAppStatusChanged(pluggedDevice: BluetoothDevice?, registered: Boolean) {
            main.post {
                log("registration: $registered")
                if (registered) {
                    retryDelay = FIRST_RETRY_MS
                    publish(LinkStatus(LinkState.READY))
                } else if (running) {
                    // Not an error. Phase 0 showed this arrives unprompted; just get it back.
                    host = null
                    scheduleRecovery("registration expired")
                }
            }
        }

        override fun onConnectionStateChanged(device: BluetoothDevice?, state: Int) {
            main.post {
                when (state) {
                    BluetoothProfile.STATE_CONNECTED -> {
                        host = device
                        lastHostAddress = device?.address
                        report.releaseAll()          // start from a known-clean report
                        log("connected to ${device.label()}")
                        publish(LinkStatus(LinkState.CONNECTED, device.label()))
                    }
                    BluetoothProfile.STATE_CONNECTING ->
                        publish(LinkStatus(LinkState.CONNECTING, device.label()))
                    else -> {
                        if (host != null) log("disconnected from ${host.label()}")
                        host = null
                        report.releaseAll()
                        publish(LinkStatus(if (running) LinkState.READY else LinkState.STOPPED))
                    }
                }
            }
        }

        override fun onGetReport(device: BluetoothDevice?, type: Byte, id: Byte, bufferSize: Int) {
            proxy?.replyReport(device, type, id, report.report())
        }

        override fun onSetReport(device: BluetoothDevice?, type: Byte, id: Byte, data: ByteArray?) {
            // Host LED state (caps/num lock). Nothing acts on it yet; Phase 2 could light the
            // Caps key from it instead of guessing.
            log("host LED state: ${data?.joinToString(" ") { "%02X".format(it) } ?: "-"}")
        }

        override fun onVirtualCableUnplug(device: BluetoothDevice?) {
            main.post {
                log("${device.label()} unplugged the keyboard")
                host = null
                publish(LinkStatus(if (running) LinkState.READY else LinkState.STOPPED))
            }
        }
    }

    // ------------------------------------------------------------------ connecting

    /** Devices already bonded to this phone. The UI offers these; the user picks one. */
    fun bondedDevices(): List<BluetoothDevice> = adapter?.bondedDevices?.toList() ?: emptyList()

    /** Returns false when the connect could not even be attempted, so the UI can say so. */
    fun connect(device: BluetoothDevice): Boolean {
        val p = proxy
        if (p == null || status.state != LinkState.READY) {
            log("connect refused: not registered")
            return false
        }
        publish(LinkStatus(LinkState.CONNECTING, device.label()))
        val ok = p.connect(device)
        if (!ok) {
            log("connect(${device.label()}) refused by the stack")
            publish(LinkStatus(LinkState.READY, detail = "could not connect to ${device.label()}"))
        }
        return ok
    }

    fun disconnect() {
        val d = host ?: return
        releaseAll()
        proxy?.disconnect(d)
    }

    // ------------------------------------------------------------------ typing

    override fun keyDown(usage: Int) { if (report.down(usage)) send() }

    override fun keyUp(usage: Int) { if (report.up(usage)) send() }

    override fun releaseAll() { if (report.releaseAll()) send() }

    private fun send() {
        val p = proxy ?: return
        val d = host ?: return
        if (!p.sendReport(d, REPORT_ID, report.report())) log("sendReport failed")
    }

    // ------------------------------------------------------------------ plumbing

    private fun publish(s: LinkStatus) {
        status = s
        onStatus?.invoke(s)
    }

    private fun fail(why: String) {
        running = false
        publish(LinkStatus(LinkState.FAILED, detail = why))
        log("FAILED: $why")
    }

    private fun log(m: String) = onLog?.invoke(m)

    private fun BluetoothDevice?.label(): String =
        if (this == null) "device" else try { name ?: address } catch (e: SecurityException) { address }

    companion object {
        /** No report id in the descriptor, so every report goes out as id 0. */
        private const val REPORT_ID = 0
        private const val FIRST_RETRY_MS = 1_000L
        private const val MAX_RETRY_MS = 30_000L

        /**
         * HID 1.11 boot keyboard, Appendix B.1 — the same descriptor Phase 0 validated and the
         * same report shape the ESP32 firmware sends. Boot protocol is the most widely
         * understood keyboard there is, which is what "any receiving device" needs.
         */
        private val REPORT_DESCRIPTOR = byteArrayOf(
            0x05, 0x01,             // Usage Page (Generic Desktop)
            0x09, 0x06,             // Usage (Keyboard)
            0xA1.toByte(), 0x01,    // Collection (Application)
            0x05, 0x07,             //   Usage Page (Keyboard/Keypad)
            0x19, 0xE0.toByte(),    //   Usage Minimum (Left Control)
            0x29, 0xE7.toByte(),    //   Usage Maximum (Right GUI)
            0x15, 0x00,             //   Logical Minimum (0)
            0x25, 0x01,             //   Logical Maximum (1)
            0x75, 0x01,             //   Report Size (1)
            0x95.toByte(), 0x08,    //   Report Count (8)
            0x81.toByte(), 0x02,    //   Input (Data,Var,Abs)   -- modifier byte
            0x95.toByte(), 0x01,    //   Report Count (1)
            0x75, 0x08,             //   Report Size (8)
            0x81.toByte(), 0x01,    //   Input (Const)          -- reserved byte
            0x95.toByte(), 0x05,    //   Report Count (5)
            0x75, 0x01,             //   Report Size (1)
            0x05, 0x08,             //   Usage Page (LEDs)
            0x19, 0x01,             //   Usage Minimum (Num Lock)
            0x29, 0x05,             //   Usage Maximum (Kana)
            0x91.toByte(), 0x02,    //   Output (Data,Var,Abs)  -- LED state from the host
            0x95.toByte(), 0x01,    //   Report Count (1)
            0x75, 0x03,             //   Report Size (3)
            0x91.toByte(), 0x01,    //   Output (Const)         -- LED padding
            0x95.toByte(), 0x06,    //   Report Count (6)
            0x75, 0x08,             //   Report Size (8)
            0x15, 0x00,             //   Logical Minimum (0)
            0x25, 0x65,             //   Logical Maximum (101)
            0x05, 0x07,             //   Usage Page (Keyboard/Keypad)
            0x19, 0x00,             //   Usage Minimum (0)
            0x29, 0x65,             //   Usage Maximum (101)
            0x81.toByte(), 0x00,    //   Input (Data,Array)     -- six key slots
            0xC0.toByte()           // End Collection
        )

        private val SDP = BluetoothHidDeviceAppSdpSettings(
            "HIDRA",
            "Phone as Bluetooth keyboard",
            "HIDRA",
            BluetoothHidDevice.SUBCLASS1_KEYBOARD,
            REPORT_DESCRIPTOR
        )
    }
}
