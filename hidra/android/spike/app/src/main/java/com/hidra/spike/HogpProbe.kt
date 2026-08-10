package com.hidra.spike

import android.annotation.SuppressLint
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.content.Context
import java.util.UUID

/**
 * Evidence for the claim in android/PLAN.md §1: a non-privileged app cannot be a BLE HID
 * peripheral, because AOSP treats the HID service UUID 0x1812 as restricted and wants
 * BLUETOOTH_PRIVILEGED (signature|privileged) before it will add it to a GATT server.
 *
 * The brief asks for "HID keyboard over BLE", so it is worth showing the door is locked
 * rather than just saying so. Expected result: addService reports a non-zero status, or the
 * service never appears. If this ever succeeds, HOGP is back on the table and the plan should
 * be revisited — so the probe is cheap insurance either way.
 */
@SuppressLint("MissingPermission")
class HogpProbe(private val context: Context, private val log: (String) -> Unit) {

    private val hidService = UUID.fromString("00001812-0000-1000-8000-00805f9b34fb")
    private val reportChar = UUID.fromString("00002a4d-0000-1000-8000-00805f9b34fb")

    private var server: BluetoothGattServer? = null

    fun run() {
        val manager = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager?
        if (manager == null) { log("HOGP probe: no BluetoothManager"); return }

        log("HOGP probe: opening GATT server…")
        server = manager.openGattServer(context, object : BluetoothGattServerCallback() {
            override fun onServiceAdded(status: Int, service: BluetoothGattService?) {
                if (status == 0 && service?.uuid == hidService) {
                    log("HOGP probe: *** addService(0x1812) SUCCEEDED *** — BLE HID may be " +
                        "possible after all; revisit PLAN.md §1")
                } else {
                    log("HOGP probe: addService(0x1812) failed, status=$status " +
                        "(expected — 0x1812 is a restricted UUID)")
                }
                close()
            }
        })

        if (server == null) { log("HOGP probe: openGattServer returned null"); return }

        val service = BluetoothGattService(hidService, BluetoothGattService.SERVICE_TYPE_PRIMARY)
        service.addCharacteristic(BluetoothGattCharacteristic(
            reportChar,
            BluetoothGattCharacteristic.PROPERTY_READ or BluetoothGattCharacteristic.PROPERTY_NOTIFY,
            BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED))

        val accepted = server!!.addService(service)
        log("HOGP probe: addService() returned $accepted (waiting for callback…)")
        if (!accepted) close()
    }

    private fun close() {
        server?.close()
        server = null
    }
}
