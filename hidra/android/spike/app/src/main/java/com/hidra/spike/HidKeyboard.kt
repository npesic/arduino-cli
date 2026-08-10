package com.hidra.spike

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothHidDevice
import android.bluetooth.BluetoothHidDeviceAppSdpSettings
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.content.Context
import java.util.concurrent.Executors

/**
 * The Phase 0 question in one class: can this phone be a Bluetooth keyboard for another device?
 *
 * Registers a boot-protocol keyboard with the HID Device profile and pushes 8-byte reports.
 * This is classic Bluetooth HID (HIDP over L2CAP), not BLE HOGP — see android/PLAN.md §1 for
 * why HOGP is not available to a non-privileged app.
 *
 * Deliberately shaped like the `HidTransport` that Phase 1 needs, so this survives the spike.
 */
@SuppressLint("MissingPermission")   // callers gate on BLUETOOTH_CONNECT; see MainActivity
class HidKeyboard(private val context: Context, private val log: (String) -> Unit) {

    /**
     * Boot keyboard, HID 1.11 Appendix B.1. Eight bytes in: modifier bitmask, one reserved
     * byte, then six key slots. That is exactly the report the ESP32 firmware sends today, so
     * tablet B sees the same keyboard it already knows how to talk to.
     *
     * No report ID in the descriptor, so every sendReport() below passes id 0.
     */
    private val reportDescriptor = byteArrayOf(
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
        0x81.toByte(), 0x02,    //   Input (Data,Var,Abs)      -- modifier byte
        0x95.toByte(), 0x01,    //   Report Count (1)
        0x75, 0x08,             //   Report Size (8)
        0x81.toByte(), 0x01,    //   Input (Const)             -- reserved byte
        0x95.toByte(), 0x05,    //   Report Count (5)
        0x75, 0x01,             //   Report Size (1)
        0x05, 0x08,             //   Usage Page (LEDs)
        0x19, 0x01,             //   Usage Minimum (Num Lock)
        0x29, 0x05,             //   Usage Maximum (Kana)
        0x91.toByte(), 0x02,    //   Output (Data,Var,Abs)     -- LED state from the host
        0x95.toByte(), 0x01,    //   Report Count (1)
        0x75, 0x03,             //   Report Size (3)
        0x91.toByte(), 0x01,    //   Output (Const)            -- LED padding
        0x95.toByte(), 0x06,    //   Report Count (6)
        0x75, 0x08,             //   Report Size (8)
        0x15, 0x00,             //   Logical Minimum (0)
        0x25, 0x65,             //   Logical Maximum (101)
        0x05, 0x07,             //   Usage Page (Keyboard/Keypad)
        0x19, 0x00,             //   Usage Minimum (0)
        0x29, 0x65,             //   Usage Maximum (101)
        0x81.toByte(), 0x00,    //   Input (Data,Array)        -- six key slots
        0xC0.toByte()           // End Collection
    )

    private val sdp = BluetoothHidDeviceAppSdpSettings(
        "HIDRA",
        "Phone as Bluetooth keyboard",
        "HIDRA",
        BluetoothHidDevice.SUBCLASS1_KEYBOARD,
        reportDescriptor
    )

    private val executor = Executors.newSingleThreadExecutor()
    private val adapter: BluetoothAdapter? =
        (context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager?)?.adapter

    private var proxy: BluetoothHidDevice? = null
    private var host: BluetoothDevice? = null

    /** Report state: modifier bitmask plus up to six held non-modifier usages (6KRO). */
    private var mods = 0
    private val keys = IntArray(6)

    var onState: ((String) -> Unit)? = null

    val isRegistered get() = proxy != null
    val connectedHost get() = host

    // ------------------------------------------------------------------ lifecycle

    fun bluetoothAvailable() = adapter != null
    fun bluetoothEnabled() = adapter?.isEnabled == true

    /** Step 1: get the HID_DEVICE proxy. Unknown #1 in PLAN.md §2 — some builds have no proxy. */
    fun start() {
        val a = adapter
        if (a == null) {
            log("FAIL: no Bluetooth adapter on this device")
            return
        }
        log("requesting HID_DEVICE profile proxy…")
        val ok = a.getProfileProxy(context, serviceListener, BluetoothProfile.HID_DEVICE)
        if (!ok) log("FAIL: getProfileProxy(HID_DEVICE) returned false — role unsupported here")
    }

    fun stop() {
        proxy?.let {
            releaseAll()
            it.unregisterApp()
            adapter?.closeProfileProxy(BluetoothProfile.HID_DEVICE, it)
            log("unregistered")
        }
        proxy = null
        host = null
        onState?.invoke("stopped")
    }

    private val serviceListener = object : BluetoothProfile.ServiceListener {
        override fun onServiceConnected(profile: Int, p: BluetoothProfile) {
            if (profile != BluetoothProfile.HID_DEVICE) return
            proxy = p as BluetoothHidDevice
            log("got HID_DEVICE proxy — registering app…")
            // Step 2: publish the SDP record. Unknown #2 in PLAN.md §2.
            val ok = proxy!!.registerApp(sdp, null, null, executor, callback)
            log(if (ok) "registerApp() accepted (waiting for onAppStatusChanged)"
                else "FAIL: registerApp() returned false")
        }

        override fun onServiceDisconnected(profile: Int) {
            if (profile != BluetoothProfile.HID_DEVICE) return
            log("HID_DEVICE proxy disconnected")
            proxy = null
            host = null
            onState?.invoke("proxy lost")
        }
    }

    private val callback = object : BluetoothHidDevice.Callback() {
        override fun onAppStatusChanged(pluggedDevice: BluetoothDevice?, registered: Boolean) {
            log("onAppStatusChanged: registered=$registered plugged=${pluggedDevice.tag()}")
            onState?.invoke(if (registered) "registered — pair from tablet B" else "not registered")
        }

        override fun onConnectionStateChanged(device: BluetoothDevice?, state: Int) {
            val name = when (state) {
                BluetoothProfile.STATE_CONNECTED -> "CONNECTED"
                BluetoothProfile.STATE_CONNECTING -> "connecting"
                BluetoothProfile.STATE_DISCONNECTED -> "disconnected"
                BluetoothProfile.STATE_DISCONNECTING -> "disconnecting"
                else -> "state $state"
            }
            log("onConnectionStateChanged: ${device.tag()} -> $name")
            host = if (state == BluetoothProfile.STATE_CONNECTED) device else null
            // Unknown #5: this is the line to watch across screen-off / host-sleep cycles.
            onState?.invoke("$name ${device.tag()}")
        }

        override fun onGetReport(device: BluetoothDevice?, type: Byte, id: Byte, bufferSize: Int) {
            log("onGetReport type=$type id=$id — replying with current state")
            proxy?.replyReport(device, type, id, currentReport())
        }

        override fun onSetReport(device: BluetoothDevice?, type: Byte, id: Byte, data: ByteArray?) {
            // The host's LED state (caps lock etc.) arrives here. Phase 0 only notes it.
            log("onSetReport type=$type id=$id data=${data?.joinToString(" ") { "%02X".format(it) }}")
        }

        override fun onSetProtocol(device: BluetoothDevice?, protocol: Byte) {
            log("onSetProtocol: ${if (protocol == BluetoothHidDevice.PROTOCOL_BOOT_MODE) "BOOT" else "REPORT"}")
        }

        override fun onVirtualCableUnplug(device: BluetoothDevice?) {
            log("onVirtualCableUnplug: ${device.tag()} — host dropped the keyboard")
            host = null
            onState?.invoke("unplugged")
        }
    }

    // ------------------------------------------------------------------ connection

    /** Hosts already bonded to this phone — Phase 0 connects to one of these by hand. */
    fun bondedDevices(): List<BluetoothDevice> = adapter?.bondedDevices?.toList() ?: emptyList()

    fun connect(device: BluetoothDevice) {
        val p = proxy
        if (p == null) { log("not registered yet"); return }
        log("connect(${device.tag()}) -> ${p.connect(device)}")
    }

    fun disconnect() {
        val d = host ?: return
        log("disconnect(${d.tag()}) -> ${proxy?.disconnect(d)}")
    }

    // ------------------------------------------------------------------ typing

    /**
     * Usages 0xE0..0xE7 fold into the modifier byte instead of taking a key slot — same rule
     * the firmware uses, so the existing keymap.js numbers work unchanged.
     */
    fun keyDown(usage: Int) {
        if (usage in 0xE0..0xE7) {
            mods = mods or (1 shl (usage - 0xE0))
        } else {
            if (keys.contains(usage)) return
            val slot = keys.indexOf(0)
            if (slot < 0) { log("rollover: six keys already held, ignoring $usage"); return }
            keys[slot] = usage
        }
        send("down 0x%02X".format(usage))
    }

    fun keyUp(usage: Int) {
        if (usage in 0xE0..0xE7) {
            mods = mods and (1 shl (usage - 0xE0)).inv()
        } else {
            val slot = keys.indexOf(usage)
            if (slot < 0) return
            keys[slot] = 0
        }
        send("up   0x%02X".format(usage))
    }

    fun releaseAll() {
        mods = 0
        keys.fill(0)
        if (host != null) send("release all")
    }

    private fun currentReport() = byteArrayOf(
        mods.toByte(), 0,
        keys[0].toByte(), keys[1].toByte(), keys[2].toByte(),
        keys[3].toByte(), keys[4].toByte(), keys[5].toByte()
    )

    /** Times the sendReport call — Phase 0 wants tap-to-character latency, not just success. */
    private fun send(what: String) {
        val p = proxy
        val d = host
        if (p == null || d == null) { log("$what — dropped, no connected host"); return }
        val t0 = System.nanoTime()
        val ok = p.sendReport(d, 0, currentReport())
        val us = (System.nanoTime() - t0) / 1000
        log("$what  ${currentReport().joinToString(" ") { "%02X".format(it) }}  " +
            "${if (ok) "ok" else "FAILED"} ${us}us")
    }
}

private fun BluetoothDevice?.tag(): String =
    if (this == null) "null" else try { "$name/$address" } catch (e: SecurityException) { address }
