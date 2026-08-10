package com.hidra

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.ArrayDeque
import java.util.UUID

/**
 * Keys out over BLE, as a HID-over-GATT keyboard. **This is the transport HIDRA uses.**
 *
 * Classic Bluetooth HID works, but the Chromebook will not list the phone: Class of Device and
 * a dozen phone profiles classify it as a phone no matter what SDP record we add, and no app
 * can change that. A BLE peripheral is classified from an advertisement *this app controls*, so
 * advertising service UUID 0x1812 sidesteps the problem. Phase 0b then found BLE also works on
 * the Fire HD 10, making it a superset of classic across every device in scope — hence one
 * transport instead of two and a picker. See PLAN.md §4, spike-hogp/RESULTS.md.
 *
 * `HidTransport` stays in the tree as unused insurance for a host that speaks classic but not
 * BLE.
 *
 * Callers must hold BLUETOOTH_CONNECT and BLUETOOTH_ADVERTISE (runtime on API 31+).
 */
@SuppressLint("MissingPermission")
class HogpTransport(context: Context) : KeyTransport {

    private val app = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val manager = app.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager?
    private val adapter = manager?.adapter
    private val prefs = app.getSharedPreferences("hidra", Context.MODE_PRIVATE)

    private val report = ReportBuilder()

    private var server: BluetoothGattServer? = null
    private var running = false
    private var advertising = false

    private val values = HashMap<BluetoothGattCharacteristic, ByteArray>()
    private val descriptorValues = HashMap<BluetoothGattDescriptor, ByteArray>()

    /** Android's GATT server takes one addService per onServiceAdded; queue or lose services. */
    private val pendingServices = ArrayDeque<BluetoothGattService>()

    private lateinit var inputReport: BluetoothGattCharacteristic
    private lateinit var batteryLevel: BluetoothGattCharacteristic

    /** Who has enabled notifications on what. A host only types once it subscribes. */
    private val subscriptions = HashMap<BluetoothGattCharacteristic, MutableSet<BluetoothDevice>>()
    private var connectedDevice: BluetoothDevice? = null

    override var status = LinkStatus(LinkState.STOPPED); private set
    override var onStatus: ((LinkStatus) -> Unit)? = null
    override var onLog: ((String) -> Unit)? = null

    val currentHost: BluetoothDevice? get() = connectedDevice

    // ------------------------------------------------------------------ lifecycle

    override fun start() {
        if (running) return
        running = true
        when {
            adapter == null -> fail("this device has no Bluetooth adapter")
            !adapter.isEnabled -> fail("Bluetooth is off")
            adapter.bluetoothLeAdvertiser == null ->
                fail("this phone cannot advertise as a BLE peripheral")
            else -> openServer()
        }
    }

    override fun stop() {
        running = false
        main.removeCallbacksAndMessages(null)
        releaseAll()
        stopAdvertising()
        unwatchBattery()
        subscriptions.clear()
        connectedDevice = null
        server?.close()
        server = null
        values.clear()
        descriptorValues.clear()
        publish(LinkStatus(LinkState.STOPPED))
    }

    private fun openServer() {
        publish(LinkStatus(LinkState.STARTING, detail = "starting keyboard…"))
        server = manager?.openGattServer(app, callback)
        if (server == null) return fail("could not open a GATT server")

        pendingServices.clear()
        pendingServices += deviceInfoService()
        pendingServices += batteryService()
        pendingServices += hidService()
        addNextService()
    }

    private fun addNextService() {
        val next = pendingServices.poll()
        if (next == null) {
            log("services registered")
            watchBattery()
            startAdvertising()
            reofferToLastHost()
            return
        }
        if (server?.addService(next) != true) fail("could not publish the ${next.uuid.short()} service")
    }

    // ------------------------------------------------------------------ advertising

    private fun startAdvertising() {
        if (advertising || !running) return
        val advertiser = adapter?.bluetoothLeAdvertiser ?: return

        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(true)
            .setTimeout(0)
            .build()

        // 0x1812 in the advertisement is the entire reason this transport exists. The device
        // name goes in the scan response: a 31-byte advertisement will not hold both, and the
        // failure is a flat ADVERTISE_FAILED_DATA_TOO_LARGE.
        val data = AdvertiseData.Builder()
            .addServiceUuid(ParcelUuid(HID_SERVICE))
            .build()
        val scanResponse = AdvertiseData.Builder()
            .setIncludeDeviceName(true)
            .build()

        advertiser.startAdvertising(settings, data, scanResponse, advertiseCallback)
    }

    private fun stopAdvertising() {
        if (!advertising) return
        adapter?.bluetoothLeAdvertiser?.stopAdvertising(advertiseCallback)
        advertising = false
    }

    private val advertiseCallback = object : AdvertiseCallback() {
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings?) {
            main.post {
                advertising = true
                log("advertising as a keyboard")
                if (connectedDevice == null) publish(LinkStatus(LinkState.READY))
            }
        }

        override fun onStartFailure(errorCode: Int) {
            main.post {
                advertising = false
                if (errorCode == ADVERTISE_FAILED_ALREADY_STARTED) { advertising = true; return@post }
                fail(when (errorCode) {
                    ADVERTISE_FAILED_DATA_TOO_LARGE -> "the advertisement is too large"
                    ADVERTISE_FAILED_TOO_MANY_ADVERTISERS -> "too many apps are advertising"
                    ADVERTISE_FAILED_FEATURE_UNSUPPORTED -> "this phone cannot advertise"
                    else -> "advertising failed (code $errorCode)"
                })
            }
        }
    }

    /**
     * A BLE peripheral cannot dial out — the host connects to us. What it *can* do is accept a
     * reconnection from a device it already knows, which is what `connect(autoConnect = true)`
     * arranges. Combined with re-advertising, that is how a real keyboard comes back after the
     * host has been asleep.
     */
    private fun reofferToLastHost() {
        val address = prefs.getString(KEY_LAST_HOST, null) ?: return
        val device = adapter?.bondedDevices?.firstOrNull { it.address == address } ?: return
        log("waiting for ${device.label()} to reconnect")
        server?.connect(device, true)
    }

    // ------------------------------------------------------------------ services

    private fun deviceInfoService() =
        BluetoothGattService(DEVICE_INFO_SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY).apply {
            addCharacteristic(readOnly(MANUFACTURER_NAME, "HIDRA".toByteArray()))
            addCharacteristic(readOnly(PNP_ID,
                byteArrayOf(0x02, 0xE0.toByte(), 0x00, 0x01, 0x00, 0x01, 0x00)))
        }

    private fun batteryService() =
        BluetoothGattService(BATTERY_SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY).apply {
            batteryLevel = BluetoothGattCharacteristic(BATTERY_LEVEL,
                BluetoothGattCharacteristic.PROPERTY_READ or
                    BluetoothGattCharacteristic.PROPERTY_NOTIFY,
                BluetoothGattCharacteristic.PERMISSION_READ)
            batteryLevel.addDescriptor(cccd())
            values[batteryLevel] = byteArrayOf(batteryPercent().toByte())
            addCharacteristic(batteryLevel)
        }

    private fun hidService() =
        BluetoothGattService(HID_SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY).apply {
            // Encrypted read forces the host to bond before it can read the report map.
            addCharacteristic(readOnly(REPORT_MAP, REPORT_DESCRIPTOR,
                BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED))

            // bcdHID 1.11, country 0, flags: RemoteWake | NormallyConnectable
            addCharacteristic(readOnly(HID_INFORMATION, byteArrayOf(0x11, 0x01, 0x00, 0x03)))

            addCharacteristic(BluetoothGattCharacteristic(HID_CONTROL_POINT,
                BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE,
                BluetoothGattCharacteristic.PERMISSION_WRITE))

            val protocolMode = BluetoothGattCharacteristic(PROTOCOL_MODE,
                BluetoothGattCharacteristic.PROPERTY_READ or
                    BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE,
                BluetoothGattCharacteristic.PERMISSION_READ or
                    BluetoothGattCharacteristic.PERMISSION_WRITE)
            values[protocolMode] = byteArrayOf(0x01)              // report protocol
            addCharacteristic(protocolMode)

            inputReport = BluetoothGattCharacteristic(REPORT,
                BluetoothGattCharacteristic.PROPERTY_READ or
                    BluetoothGattCharacteristic.PROPERTY_NOTIFY,
                BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED)
            inputReport.addDescriptor(cccd())
            // Report Reference [id, type]; type 1 = Input. Without it the host reads the service
            // and ignores it.
            inputReport.addDescriptor(reportReference(REPORT_ID, INPUT_REPORT))
            values[inputReport] = report.report()
            addCharacteristic(inputReport)

            val output = BluetoothGattCharacteristic(REPORT,
                BluetoothGattCharacteristic.PROPERTY_READ or
                    BluetoothGattCharacteristic.PROPERTY_WRITE or
                    BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE,
                BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED or
                    BluetoothGattCharacteristic.PERMISSION_WRITE_ENCRYPTED)
            output.addDescriptor(reportReference(REPORT_ID, OUTPUT_REPORT))
            values[output] = byteArrayOf(0)
            addCharacteristic(output)
        }

    private fun readOnly(
        uuid: UUID,
        value: ByteArray,
        permission: Int = BluetoothGattCharacteristic.PERMISSION_READ
    ) = BluetoothGattCharacteristic(uuid, BluetoothGattCharacteristic.PROPERTY_READ, permission)
        .also { values[it] = value }

    private fun cccd() = BluetoothGattDescriptor(CCCD,
        BluetoothGattDescriptor.PERMISSION_READ or BluetoothGattDescriptor.PERMISSION_WRITE)
        .also { descriptorValues[it] = byteArrayOf(0, 0) }

    private fun reportReference(id: Int, type: Int) =
        BluetoothGattDescriptor(REPORT_REFERENCE, BluetoothGattDescriptor.PERMISSION_READ)
            .also { descriptorValues[it] = byteArrayOf(id.toByte(), type.toByte()) }

    // ------------------------------------------------------------------ gatt server

    private val callback = object : BluetoothGattServerCallback() {

        override fun onServiceAdded(status: Int, service: BluetoothGattService?) {
            main.post { addNextService() }
        }

        override fun onConnectionStateChange(device: BluetoothDevice?, status: Int, newState: Int) {
            main.post {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    connectedDevice = device
                    device?.let { prefs.edit().putString(KEY_LAST_HOST, it.address).apply() }
                    log("connected to ${device.label()}")
                    // Connected is not the same as usable: nothing types until the host
                    // subscribes to the input report.
                    publish(LinkStatus(LinkState.CONNECTING, device.label(),
                        "connected, waiting for the device to accept the keyboard"))
                } else {
                    log("disconnected from ${connectedDevice.label()}")
                    connectedDevice = null
                    device?.let { d -> subscriptions.values.forEach { it.remove(d) } }
                    report.releaseAll()
                    if (running) {
                        publish(LinkStatus(LinkState.READY))
                        // The spike never did this, so recovery meant restarting by hand.
                        // Re-advertising is how a BLE keyboard makes itself findable again.
                        advertising = false
                        main.postDelayed({ startAdvertising(); reofferToLastHost() }, READVERTISE_MS)
                    } else {
                        publish(LinkStatus(LinkState.STOPPED))
                    }
                }
            }
        }

        override fun onCharacteristicReadRequest(
            device: BluetoothDevice?, requestId: Int, offset: Int,
            characteristic: BluetoothGattCharacteristic?
        ) = respond(device, requestId, offset, values[characteristic])

        override fun onDescriptorReadRequest(
            device: BluetoothDevice?, requestId: Int, offset: Int,
            descriptor: BluetoothGattDescriptor?
        ) = respond(device, requestId, offset, descriptorValues[descriptor])

        override fun onDescriptorWriteRequest(
            device: BluetoothDevice?, requestId: Int, descriptor: BluetoothGattDescriptor?,
            preparedWrite: Boolean, responseNeeded: Boolean, offset: Int, value: ByteArray?
        ) {
            if (descriptor != null && value != null) descriptorValues[descriptor] = value

            if (descriptor?.uuid == CCCD && device != null) {
                val on = value != null && value.isNotEmpty() && value[0].toInt() and 0x01 != 0
                val target = descriptor.characteristic
                val set = subscriptions.getOrPut(target) { mutableSetOf() }
                if (on) set += device else set -= device

                if (target === inputReport) main.post {
                    log(if (on) "the device accepted the keyboard" else "the device dropped the keyboard")
                    publish(if (on) LinkStatus(LinkState.CONNECTED, device.label())
                            else LinkStatus(LinkState.CONNECTING, device.label(),
                                "connected, but the device is not accepting keys"))
                }
            }
            if (responseNeeded) respond(device, requestId, offset, value)
        }

        override fun onCharacteristicWriteRequest(
            device: BluetoothDevice?, requestId: Int, characteristic: BluetoothGattCharacteristic?,
            preparedWrite: Boolean, responseNeeded: Boolean, offset: Int, value: ByteArray?
        ) {
            if (characteristic != null && value != null) values[characteristic] = value
            if (responseNeeded) respond(device, requestId, offset, value)
        }
    }

    private fun respond(device: BluetoothDevice?, requestId: Int, offset: Int, value: ByteArray?) {
        val payload = when {
            value == null -> ByteArray(0)
            offset >= value.size -> ByteArray(0)
            offset > 0 -> value.copyOfRange(offset, value.size)
            else -> value
        }
        server?.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, payload)
    }

    // ------------------------------------------------------------------ typing

    override fun keyDown(usage: Int) { if (report.down(usage)) sendReport() }

    override fun keyUp(usage: Int) { if (report.up(usage)) sendReport() }

    override fun releaseAll() { if (report.releaseAll()) sendReport() }

    /** Report id lives in the Report Reference descriptor, so the payload is the bare 8 bytes. */
    private fun sendReport() {
        val bytes = report.report()
        values[inputReport] = bytes
        notify(inputReport, bytes)
    }

    private fun notify(characteristic: BluetoothGattCharacteristic, bytes: ByteArray) {
        val s = server ?: return
        val devices = subscriptions[characteristic] ?: return
        for (device in devices.toList()) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                s.notifyCharacteristicChanged(device, characteristic, false, bytes)
            } else {
                @Suppress("DEPRECATION")
                run {
                    characteristic.value = bytes
                    s.notifyCharacteristicChanged(device, characteristic, false)
                }
            }
        }
    }

    // ------------------------------------------------------------------ battery

    /**
     * The host thinks this is a keyboard, so it will show a battery for it. Reporting the
     * phone's real charge is more honest than the spike's hardcoded 100%, and it is the number
     * the user would want anyway.
     */
    private val batteryReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (!::batteryLevel.isInitialized) return
            val percent = batteryPercent()
            val current = values[batteryLevel]?.firstOrNull()?.toInt() ?: -1
            if (percent == current) return
            values[batteryLevel] = byteArrayOf(percent.toByte())
            notify(batteryLevel, byteArrayOf(percent.toByte()))
        }
    }

    private var watchingBattery = false

    private fun watchBattery() {
        if (watchingBattery) return
        app.registerReceiver(batteryReceiver, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        watchingBattery = true
    }

    private fun unwatchBattery() {
        if (!watchingBattery) return
        runCatching { app.unregisterReceiver(batteryReceiver) }
        watchingBattery = false
    }

    /** The phone's charge, which the host displays as the keyboard's battery. */
    fun batteryPercent(): Int {
        val bm = app.getSystemService(Context.BATTERY_SERVICE) as BatteryManager?
        val level = bm?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1
        return level.coerceIn(0, 100).let { if (it == 0) 100 else it }
    }

    // ------------------------------------------------------------------ plumbing

    /** Drops the current host. It can reconnect: we keep advertising. */
    fun disconnect() {
        val d = connectedDevice ?: return
        releaseAll()
        server?.cancelConnection(d)
    }

    /** Stop offering ourselves to the remembered host — the "start fresh" button. */
    fun forgetLastHost() {
        prefs.edit().remove(KEY_LAST_HOST).apply()
        log("forgot the last device")
    }

    private fun publish(s: LinkStatus) {
        status = s
        onStatus?.invoke(s)
    }

    private fun fail(why: String) {
        running = false
        publish(LinkStatus(LinkState.FAILED, detail = why))
        log("failed: $why")
    }

    private fun log(m: String) = onLog?.invoke(m)

    private fun UUID?.short(): String =
        this?.toString()?.substring(4, 8)?.uppercase()?.let { "0x$it" } ?: "?"

    private fun BluetoothDevice?.label(): String =
        if (this == null) "device" else try { name ?: address } catch (e: SecurityException) { address }

    companion object {
        private const val KEY_LAST_HOST = "lastHost"
        private const val READVERTISE_MS = 500L

        private const val REPORT_ID = 1
        private const val INPUT_REPORT = 1
        private const val OUTPUT_REPORT = 2

        private fun uuid16(v: String) = UUID.fromString("0000$v-0000-1000-8000-00805f9b34fb")

        val HID_SERVICE: UUID = uuid16("1812")
        val REPORT_MAP: UUID = uuid16("2a4b")
        val HID_INFORMATION: UUID = uuid16("2a4a")
        val HID_CONTROL_POINT: UUID = uuid16("2a4c")
        val PROTOCOL_MODE: UUID = uuid16("2a4e")
        val REPORT: UUID = uuid16("2a4d")
        val REPORT_REFERENCE: UUID = uuid16("2908")
        val CCCD: UUID = uuid16("2902")
        val BATTERY_SERVICE: UUID = uuid16("180f")
        val BATTERY_LEVEL: UUID = uuid16("2a19")
        val DEVICE_INFO_SERVICE: UUID = uuid16("180a")
        val PNP_ID: UUID = uuid16("2a50")
        val MANUFACTURER_NAME: UUID = uuid16("2a29")

        /** Boot keyboard layout with an explicit Report ID, matching the Report Reference. */
        private val REPORT_DESCRIPTOR = byteArrayOf(
            0x05, 0x01,             // Usage Page (Generic Desktop)
            0x09, 0x06,             // Usage (Keyboard)
            0xA1.toByte(), 0x01,    // Collection (Application)
            0x85.toByte(), 0x01,    //   Report ID (1)
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
            0x91.toByte(), 0x02,    //   Output (Data,Var,Abs)  -- LED state
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
    }
}
