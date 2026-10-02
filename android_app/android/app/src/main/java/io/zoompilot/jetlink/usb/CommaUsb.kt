package io.zoompilot.jetlink.usb

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.hardware.usb.UsbConstants
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbEndpoint
import android.hardware.usb.UsbInterface
import android.hardware.usb.UsbManager
import android.util.Log
import io.zoompilot.jetlink.server.Native
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Where the comma's USB link stands, as this phone sees it. */
sealed interface UsbState {
    /** Nothing jetlink is on the USB port. */
    data object None : UsbState

    /** The comma is plugged in, and Android has not let Jetlink use it yet. */
    data object NeedsPermission : UsbState

    /** The server has the comma's gadget. */
    data object Attached : UsbState

    data class Failed(val reason: String) : UsbState
}

/**
 * The comma's USB gadget, as Android hands it to an app: found by its IDs,
 * opened once Android allows it, its vendor interface claimed, and the
 * connection's file descriptor passed to the server, which does the bulk
 * transfers itself (UsbfsPipes.swift). Android's own bulkTransfer loses what
 * arrived when it times out and cannot be woken, so it is not used.
 */
class CommaUsb(private val context: Context) {
    private val manager = context.getSystemService(UsbManager::class.java)
    private val state = MutableStateFlow<UsbState>(UsbState.None)
    val usb: StateFlow<UsbState> = state.asStateFlow()

    private var open: Opened? = null

    private class Opened(val device: UsbDevice, val connection: UsbDeviceConnection, val iface: UsbInterface)

    /** The comma's gadget, if it is on the bus. */
    fun find(): UsbDevice? = manager.deviceList.values.firstOrNull(::isComma)

    /**
     * Opens the gadget if there is one and Android allows it, asking once if
     * it does not. Safe to call again; an open gadget is left alone.
     */
    @Synchronized
    fun connect() {
        val device = find()
        if (device == null) {
            if (open != null) disconnect()
            state.value = UsbState.None
            return
        }
        if (open?.device?.deviceName == device.deviceName) return
        if (!manager.hasPermission(device)) {
            state.value = UsbState.NeedsPermission
            requestPermission(device)
            return
        }
        attach(device)
    }

    private fun attach(device: UsbDevice) {
        disconnect()
        if (!Native.loaded) return fail("libjetlink.so is missing; the server cannot take the link")
        val iface = linkInterface(device) ?: return fail("the comma's gadget has no vendor interface")
        val bulkIn = endpoint(iface, UsbConstants.USB_DIR_IN) ?: return fail("the gadget's interface has no bulk IN endpoint")
        val bulkOut = endpoint(iface, UsbConstants.USB_DIR_OUT) ?: return fail("the gadget's interface has no bulk OUT endpoint")
        val connection = manager.openDevice(device) ?: return fail("Android would not open the comma")
        if (!connection.claimInterface(iface, true)) {
            connection.close()
            return fail("another app holds the comma's interface")
        }
        val error = Native.usbAttach(connection.fileDescriptor, bulkIn.address, bulkOut.address)
        if (error != null) {
            connection.releaseInterface(iface)
            connection.close()
            return fail(error)
        }
        open = Opened(device, connection, iface)
        state.value = UsbState.Attached
        Log.i(TAG, "comma attached: ${device.deviceName}, endpoints ${hex(bulkIn.address)} in, ${hex(bulkOut.address)} out")
    }

    /** Lets the gadget go: the server first, so nothing uses the descriptor when it closes. */
    @Synchronized
    fun disconnect() {
        val current = open ?: return
        open = null
        if (Native.loaded) Native.usbDetach()
        current.connection.releaseInterface(current.iface)
        current.connection.close()
        state.value = UsbState.None
    }

    /** A device went away; lets it go if it was the comma. */
    @Synchronized
    fun detached(device: UsbDevice?) {
        if (device == null || open?.device?.deviceName == device.deviceName) disconnect()
        if (find() == null) state.value = UsbState.None
    }

    private fun fail(reason: String) {
        Log.w(TAG, "comma not attached: $reason")
        state.value = UsbState.Failed(reason)
    }

    private fun requestPermission(device: UsbDevice) {
        // Mutable, so UsbManager can add the device and the answer; explicit,
        // as Android 14 requires of a mutable PendingIntent.
        val intent = Intent(ACTION_PERMISSION).setPackage(context.packageName)
        val pending = PendingIntent.getBroadcast(context, 0, intent, PendingIntent.FLAG_MUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        manager.requestPermission(device, pending)
    }

    companion object {
        private const val TAG = "jetlink"
        const val ACTION_PERMISSION = "io.zoompilot.jetlink.USB_PERMISSION"

        /** The gadget's IDs and its link interface's class (Pinned.swift, from the Python). */
        const val VENDOR_ID = 0x1209
        const val PRODUCT_ID = 0x0001
        const val VENDOR_CLASS = 0xFF

        fun isComma(device: UsbDevice): Boolean = device.vendorId == VENDOR_ID && device.productId == PRODUCT_ID

        /**
         * The vendor-class interface, wherever the gadget put it (the comma
         * can also present a network interface), else interface 0, where the
         * gadget script puts the link first.
         */
        fun linkInterface(device: UsbDevice): UsbInterface? {
            val all = (0 until device.interfaceCount).map(device::getInterface)
            return all.firstOrNull {
                it.interfaceClass == VENDOR_CLASS && it.interfaceSubclass == VENDOR_CLASS && it.interfaceProtocol == VENDOR_CLASS
            } ?: all.firstOrNull { it.id == 0 }
        }

        /** The interface's bulk endpoint in `direction`; addresses come from the descriptors, never assumed. */
        fun endpoint(iface: UsbInterface, direction: Int): UsbEndpoint? =
            (0 until iface.endpointCount).map(iface::getEndpoint)
                .firstOrNull { it.type == UsbConstants.USB_ENDPOINT_XFER_BULK && it.direction == direction }

        private fun hex(address: Int) = "%02x".format(address)
    }
}
