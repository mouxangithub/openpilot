package io.zoompilot.jetlink.server

import io.zoompilot.jetlink.usb.CommaUsb
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

/**
 * The few constants the Android side cannot take from the server, checked
 * against Pinned.swift, which is generated from the Python: the gadget's IDs
 * in the device filter and in CommaUsb, the port, the onnxruntime
 * release, and the NDK the Swift SDK was built with.
 */
class PinnedTest {
    private val pinned = File(SnapshotTest.REPO, "JetlinkKit/Sources/JetlinkKit/Pinned.swift").readText()

    private fun pinnedInt(name: String): Int {
        val value = Regex("""static let $name: \w+ = (0x[0-9A-Fa-f]+|\d+)""").find(pinned)?.groupValues?.get(1)
            ?: error("Pinned.$name not found")
        return if (value.startsWith("0x")) value.substring(2).toInt(16) else value.toInt()
    }

    @Test
    fun theGadgetIDs() {
        assertEquals(pinnedInt("usbVendorID"), CommaUsb.VENDOR_ID)
        assertEquals(pinnedInt("usbProductID"), CommaUsb.PRODUCT_ID)
        assertEquals(listOf(0xFF, 0xFF, 0xFF), List(3) { CommaUsb.VENDOR_CLASS })
        val filter = File(SnapshotTest.REPO, "android/app/src/main/res/xml/device_filter.xml").readText()
        assertEquals(pinnedInt("usbVendorID").toString(), Regex("""vendor-id="(\d+)"""").find(filter)?.groupValues?.get(1))
        assertEquals(pinnedInt("usbProductID").toString(), Regex("""product-id="(\d+)"""").find(filter)?.groupValues?.get(1))
    }

    @Test
    fun thePort() {
        assertEquals(pinnedInt("defaultPort"), io.zoompilot.jetlink.settings.SettingsValues().port)
    }

    @Test
    fun theNdk() {
        val env = File(SnapshotTest.REPO, "android/scripts/swift-env.sh").readText()
        val gradle = File(SnapshotTest.REPO, "android/app/build.gradle.kts").readText()
        assertEquals(
            Regex("""NDK_VERSION=(\S+)""").find(env)?.groupValues?.get(1),
            Regex("""ndkVersion = "([^"]+)"""").find(gradle)?.groupValues?.get(1),
        )
    }

    @Test
    fun theOnnxruntimeRelease() {
        val swift = Regex("""static let onnxruntimeVersion: String = "([^"]+)"""").find(pinned)?.groupValues?.get(1)
        val toml = File(SnapshotTest.REPO, "android/gradle/libs.versions.toml").readText()
        val gradle = Regex("""onnxruntime = "([^"]+)"""").find(toml)?.groupValues?.get(1)
        assertEquals(swift, gradle)
    }
}
