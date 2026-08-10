package com.hidra.hogp

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
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import java.util.ArrayDeque
import java.util.UUID

/**
 * Phase 0b — HID over GATT (HOGP), the BLE route.
 *
 * Why this exists: the Chromebook sees the phone during a scan and reads its service list —
 * including the HID UUID 0x1124 — but still filters it out of the Bluetooth settings list,
 * because the adapter's Class of Device and its dozen phone profiles classify it as a phone.
 * An app cannot change that. A BLE peripheral, however, is classified from an advertisement
 * *this app controls*, so advertising service UUID 0x1812 sidesteps the problem instead of
 * fighting it.
 *
 * The single question: **does the Chromebook list this as an input device, and does it type?**
 *
 * A HOGP keyboard needs all of this present before a host takes it seriously:
 *
 *   Device Information (0x180A) — PnP ID, manufacturer
 *   Battery (0x180F)            — hosts expect a battery on an input peripheral
 *   HID (0x1812)                — report map, HID info, control point, protocol mode,
 *                                 input report (notify + CCCD + report reference),
 *                                 output report for LEDs
 */
@SuppressLint("MissingPermission")
class HogpPeripheral(private val context: Context, private val log: (String) -> Unit) {

    private val main = Handler(Looper.getMainLooper())
    private val manager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager?
    private val adapter = manager?.adapter

    private var server: BluetoothGattServer? = null
    private var advertising = false

    /** Static characteristic values, served from onCharacteristicReadRequest. */
    private val values = HashMap<BluetoothGattCharacteristic, ByteArray>()
    private val descriptorValues = HashMap<BluetoothGattDescriptor, ByteArray>()

    /**
     * Android's GATT server accepts one addService at a time — the next must wait for
     * onServiceAdded. Getting this wrong silently drops services, which then looks exactly like
     * a host compatibility problem. Hence the queue.
     */
    private val pendingServices = ArrayDeque<BluetoothGattService>()

    private lateinit var inputReport: BluetoothGattCharacteristic
    private val subscribers = mutableSetOf<BluetoothDevice>()

    /** Report state: modifier bitmask + six key slots, same rules as the classic build. */
    private var mods = 0
    private val slots = IntArray(6)

    var onState: ((String) -> Unit)? = null

    // ------------------------------------------------------------------ lifecycle

    fun start() {
        if (adapter == null) { log("FAIL: no Bluetooth adapter"); return }
        if (!adapter.isEnabled) { log("FAIL: Bluetooth is off"); return }

        log("opening GATT server…")
        server = manager?.openGattServer(context, callback)
        if (server == null) { log("FAIL: openGattServer returned null"); return }

        pendingServices.clear()
        pendingServices += deviceInfoService()
        pendingServices += batteryService()
        pendingServices += hidService()
        addNextService()
    }

    fun stop() {
        stopAdvertising()
        subscribers.clear()
        server?.close()
        server = null
        values.clear()
        descriptorValues.clear()
        log("stopped")
        onState?.invoke("stopped")
    }

    private fun addNextService() {
        val next = pendingServices.poll()
        if (next == null) {
            log("all services registered")
            startAdvertising()
            return
        }
        if (server?.addService(next) != true) log("FAIL: addService(${next.uuid.short()}) refused")
    }

    // ------------------------------------------------------------------ advertising

    /**
     * The whole point of Phase 0b: 0x1812 goes in the advertisement, where the host reads it
     * before any connection and classifies us from it.
     *
     * The device name goes in the scan response rather than the advertisement — 31 bytes will
     * not hold a long phone name alongside the UUID, and the failure mode is a flat
     * ADVERTISE_FAILED_DATA_TOO_LARGE.
     */
    private fun startAdvertising() {
        val advertiser = adapter?.bluetoothLeAdvertiser
        if (advertiser == null) { log("FAIL: no BLE advertiser on this phone"); return }

        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(true)
            .setTimeout(0)
            .build()

        val data = AdvertiseData.Builder()
            .setIncludeTxPowerLevel(false)
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
            advertising = true
            log("advertising 0x1812 — now look for this phone on the receiving device")
            onState?.invoke("advertising as a keyboard")
        }

        override fun onStartFailure(errorCode: Int) {
            advertising = false
            val why = when (errorCode) {
                ADVERTISE_FAILED_DATA_TOO_LARGE -> "advertisement too large"
                ADVERTISE_FAILED_TOO_MANY_ADVERTISERS -> "too many advertisers"
                ADVERTISE_FAILED_ALREADY_STARTED -> "already advertising"
                ADVERTISE_FAILED_INTERNAL_ERROR -> "internal error"
                ADVERTISE_FAILED_FEATURE_UNSUPPORTED -> "peripheral mode unsupported on this phone"
                else -> "code $errorCode"
            }
            log("FAIL: advertising did not start — $why")
            onState?.invoke("not advertising")
        }
    }

    // ------------------------------------------------------------------ services

    private fun deviceInfoService() =
        BluetoothGattService(DEVICE_INFO_SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY).apply {
            addCharacteristic(readOnly(MANUFACTURER_NAME, "HIDRA".toByteArray()))
            // PnP ID: vendor id source = USB, vendor, product, version. Hosts use this for quirk
            // lookups; a plausible value keeps us off the unknown-device path.
            addCharacteristic(readOnly(PNP_ID,
                byteArrayOf(0x02, 0xE0.toByte(), 0x00, 0x01, 0x00, 0x01, 0x00)))
        }

    private fun batteryService() =
        BluetoothGattService(BATTERY_SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY).apply {
            val level = BluetoothGattCharacteristic(BATTERY_LEVEL,
                BluetoothGattCharacteristic.PROPERTY_READ or
                    BluetoothGattCharacteristic.PROPERTY_NOTIFY,
                BluetoothGattCharacteristic.PERMISSION_READ)
            level.addDescriptor(cccd())
            values[level] = byteArrayOf(100)
            addCharacteristic(level)
        }

    private fun hidService() =
        BluetoothGattService(HID_SERVICE, BluetoothGattService.SERVICE_TYPE_PRIMARY).apply {
            // Encrypted read permission is what forces the host to bond before it can read the
            // report map — HOGP requires an encrypted link.
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
            values[protocolMode] = byteArrayOf(0x01)          // report protocol
            addCharacteristic(protocolMode)

            // Input report: the characteristic keystrokes are notified on.
            inputReport = BluetoothGattCharacteristic(REPORT,
                BluetoothGattCharacteristic.PROPERTY_READ or
                    BluetoothGattCharacteristic.PROPERTY_NOTIFY,
                BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED)
            inputReport.addDescriptor(cccd())
            // Report Reference [report id, type]; type 1 = Input. Without it the host cannot
            // tell which report this characteristic carries and ignores the service.
            inputReport.addDescriptor(reportReference(REPORT_ID, INPUT_REPORT))
            values[inputReport] = report()
            addCharacteristic(inputReport)

            // Output report — the host's LED state (caps lock and friends).
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
            main.post {
                log("service ${service?.uuid.short()} added, status=$status")
                addNextService()
            }
        }

        override fun onConnectionStateChange(device: BluetoothDevice?, status: Int, newState: Int) {
            main.post {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    log("GATT connected: ${device?.label()}")
                    onState?.invoke("connected to ${device?.label()}")
                } else {
                    device?.let { subscribers.remove(it) }
                    log("GATT disconnected: ${device?.label()} (status $status)")
                    onState?.invoke(if (advertising) "advertising as a keyboard" else "idle")
                }
            }
        }

        override fun onCharacteristicReadRequest(
            device: BluetoothDevice?, requestId: Int, offset: Int,
            characteristic: BluetoothGattCharacteristic?
        ) {
            val value = values[characteristic]
            log("read ${characteristic?.uuid.short()} offset=$offset -> ${value?.size ?: 0} bytes")
            respond(device, requestId, offset, value)
        }

        override fun onDescriptorReadRequest(
            device: BluetoothDevice?, requestId: Int, offset: Int,
            descriptor: BluetoothGattDescriptor?
        ) {
            val value = descriptorValues[descriptor]
            log("read descriptor ${descriptor?.uuid.short()} -> " +
                (value?.joinToString(" ") { "%02X".format(it) } ?: "-"))
            respond(device, requestId, offset, value)
        }

        override fun onDescriptorWriteRequest(
            device: BluetoothDevice?, requestId: Int, descriptor: BluetoothGattDescriptor?,
            preparedWrite: Boolean, responseNeeded: Boolean, offset: Int, value: ByteArray?
        ) {
            if (descriptor != null && value != null) descriptorValues[descriptor] = value
            // A CCCD write on the input report is the moment the host commits to treating us as
            // a keyboard. This is the strongest single signal Phase 0b can produce.
            if (descriptor?.uuid == CCCD && descriptor.characteristic === inputReport) {
                val on = value != null && value.isNotEmpty() && value[0].toInt() and 0x01 != 0
                if (on && device != null) subscribers += device else device?.let { subscribers.remove(it) }
                log(if (on) "*** host SUBSCRIBED to the input report — it is treating us as a keyboard ***"
                    else "host unsubscribed from the input report")
                main.post { onState?.invoke(if (on) "keyboard live" else "connected, not subscribed") }
            }
            if (responseNeeded) respond(device, requestId, offset, value)
        }

        override fun onCharacteristicWriteRequest(
            device: BluetoothDevice?, requestId: Int, characteristic: BluetoothGattCharacteristic?,
            preparedWrite: Boolean, responseNeeded: Boolean, offset: Int, value: ByteArray?
        ) {
            if (characteristic != null && value != null) values[characteristic] = value
            log("write ${characteristic?.uuid.short()} = " +
                (value?.joinToString(" ") { "%02X".format(it) } ?: "-"))
            if (responseNeeded) respond(device, requestId, offset, value)
        }

        override fun onMtuChanged(device: BluetoothDevice?, mtu: Int) = log("MTU = $mtu")
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

    fun keyDown(usage: Int) {
        if (usage in 0xE0..0xE7) mods = mods or (1 shl (usage - 0xE0))
        else {
            if (slots.contains(usage)) return
            val free = slots.indexOf(0)
            if (free < 0) return
            slots[free] = usage
        }
        notifyReport("down 0x%02X".format(usage))
    }

    fun keyUp(usage: Int) {
        if (usage in 0xE0..0xE7) mods = mods and (1 shl (usage - 0xE0)).inv()
        else {
            val at = slots.indexOf(usage)
            if (at < 0) return
            slots[at] = 0
        }
        notifyReport("up   0x%02X".format(usage))
    }

    fun releaseAll() {
        mods = 0
        slots.fill(0)
        notifyReport("release all")
    }

    private fun report() = byteArrayOf(
        mods.toByte(), 0,
        slots[0].toByte(), slots[1].toByte(), slots[2].toByte(),
        slots[3].toByte(), slots[4].toByte(), slots[5].toByte()
    )

    /**
     * The report id lives in the Report Reference descriptor, not in the payload, so what goes
     * out is the bare 8 bytes — byte for byte the report the classic build sends.
     */
    private fun notifyReport(what: String) {
        val s = server ?: return
        val bytes = report()
        values[inputReport] = bytes
        if (subscribers.isEmpty()) { log("$what — dropped, host is not subscribed"); return }
        for (device in subscribers.toList()) {
            val ok = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                s.notifyCharacteristicChanged(device, inputReport, false, bytes) == STATUS_SUCCESS
            } else {
                @Suppress("DEPRECATION")
                run {
                    inputReport.value = bytes
                    s.notifyCharacteristicChanged(device, inputReport, false)
                }
            }
            log("$what  ${bytes.joinToString(" ") { "%02X".format(it) }}  ${if (ok) "ok" else "FAILED"}")
        }
    }

    private fun UUID?.short(): String =
        this?.toString()?.substring(4, 8)?.uppercase()?.let { "0x$it" } ?: "?"

    private fun BluetoothDevice.label(): String =
        try { name ?: address } catch (e: SecurityException) { address }

    companion object {
        /** BluetoothStatusCodes.SUCCESS, inlined so the code still compiles below API 33. */
        private const val STATUS_SUCCESS = 0

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

        /**
         * Boot keyboard layout, plus a Report ID item — HOGP identifies reports through the
         * Report Reference descriptor, and an explicit id keeps map and descriptor agreeing.
         */
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
