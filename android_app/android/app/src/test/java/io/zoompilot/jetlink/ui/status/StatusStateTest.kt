package io.zoompilot.jetlink.ui.status

import io.zoompilot.jetlink.device.DeviceHealth
import io.zoompilot.jetlink.server.CatalogInfo
import io.zoompilot.jetlink.server.Engine
import io.zoompilot.jetlink.server.Link
import io.zoompilot.jetlink.server.Medium
import io.zoompilot.jetlink.server.RunState
import io.zoompilot.jetlink.server.Snapshot
import io.zoompilot.jetlink.server.SnapshotTest
import io.zoompilot.jetlink.ui.PreviewData
import io.zoompilot.jetlink.ui.Tone
import io.zoompilot.jetlink.usb.UsbState
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File
import java.util.Locale

/** What the Status tab says for each state, as the iPhone's StatusState says it. */
class StatusStateTest {
    private val fixture = Snapshot.parse(
        File(SnapshotTest.REPO, "JetlinkKit/Tests/JetlinkKitTests/Fixtures/android_snapshot.json").readText(),
    )
    private lateinit var locale: Locale

    @Before
    fun englishNumbers() {
        locale = Locale.getDefault()
        Locale.setDefault(Locale.US)
    }

    @After
    fun restore() {
        Locale.setDefault(locale)
    }

    @Test
    fun servingTheComma() {
        val state = StatusState(RunState.Serving, fixture)
        assertTrue(state.isServingFrames)
        assertEquals(StatusState.Hero.Budget(fixture.recent), state.hero)
        assertEquals(StatusState.Summary.Connected, state.summary)
        assertEquals("Connected over USB 3 · BMRLNAP Model v4", state.subtitle)
        assertEquals("11.6 ms headroom", state.accessoryDetail)
        assertEquals("Connected", state.linkNote)
    }

    @Test
    fun usb2IsOrange() {
        val state = StatusState(RunState.Serving, fixture.copy(medium = Medium("usb2", "USB 2", slow = true)))
        assertEquals(StatusState.Summary.ConnectedSlow, state.summary)
        assertEquals(Tone.Warning, state.summary.tone)
        assertEquals("Connected over USB 2", state.headline)
        assertEquals("Slow, use USB 3", state.linkNote)
    }

    @Test
    fun waitingForTheComma() {
        val waiting = fixture.copy(link = Link(state = "waiting"), medium = null, recent = null)
        val state = StatusState(RunState.Serving, waiting)
        assertEquals(StatusState.Hero.Waiting, state.hero)
        assertEquals("Waiting for Comma · BMRLNAP Model v4", state.subtitle)
        assertEquals("BMRLNAP Model v4", state.accessoryDetail)
        assertEquals("Waiting", state.linkNote)
        assertEquals("Plug in the comma.", state.waitingDescription)
        val plugged = state.copy(usb = UsbState.Attached)
        assertEquals("Connecting", plugged.linkNote)
        assertEquals("Connecting over USB.", plugged.waitingDescription)
    }

    @Test
    fun androidHasNotAllowedUsb() {
        val waiting = fixture.copy(link = Link(state = "waiting"), medium = null, recent = null)
        val state = StatusState(RunState.Serving, waiting, usb = UsbState.NeedsPermission)
        assertEquals(StatusState.Summary.AllowUsb, state.summary)
        assertEquals(StatusState.Hero.Waiting, state.hero)
    }

    @Test
    fun preparingAModel() {
        val state = StatusState(RunState.Serving, PreviewData.preparing)
        assertTrue(state.hero is StatusState.Hero.Progress)
        assertEquals("Preparing Model · Cinque Terre Model V3", state.subtitle)
    }

    @Test
    fun noModelYet() {
        val state = StatusState(RunState.Serving, PreviewData.empty)
        assertEquals(StatusState.Hero.NoModel, state.hero)
        assertEquals("Cinque Terre Model V3", state.defaultModel?.displayName)
        assertFalse(state.catalogUnavailable)
        val offline = PreviewData.empty.copy(catalog = CatalogInfo(error = "no network", count = 0))
        assertTrue(StatusState(RunState.Serving, offline).catalogUnavailable)
    }

    @Test
    fun aConnectedCommaWithoutAModel() {
        val state = StatusState(RunState.Serving, fixture.copy(engine = Engine()))
        assertEquals(StatusState.Summary.NoModel, state.summary)
    }

    @Test
    fun failures() {
        val failed = StatusState(RunState.Failed("no libjetlink"), fixture)
        assertEquals(StatusState.Hero.Failed(model = false), failed.hero)
        assertEquals("Stopped", failed.summary.title)
        assertEquals(Tone.Bad, failed.summary.tone)
        val model = StatusState(RunState.Serving, fixture.copy(engine = Engine(state = "failed", sha256 = PreviewData.BIG_MODEL_SHA)))
        assertEquals(StatusState.Hero.Failed(model = true), model.hero)
        assertEquals("Model Failed · BMRLNAP Model v4", model.subtitle)
    }

    @Test
    fun stoppedAndStarting() {
        assertEquals(StatusState.Hero.Stopped, StatusState(RunState.Stopped, fixture).hero)
        assertEquals("Stopped · BMRLNAP Model v4", StatusState(RunState.Stopped, fixture).subtitle)
        assertEquals("Starting", StatusState(RunState.Starting, Snapshot()).subtitle)
    }

    @Test
    fun phoneTiles() {
        val health = DeviceHealth(thermal = "serious", batteryTemp = 41.6f, batteryLevel = 15, charging = false, availableMemory = 800_000_000)
        assertEquals("Hot", DeviceText.thermal(health).title)
        assertEquals("Throttling", DeviceText.temperatureNote(health))
        assertEquals("Battery 34 °C", DeviceText.temperatureNote(DeviceHealth(batteryTemp = 34.2f)))
        assertEquals("15", DeviceText.batteryValue(health))
        assertEquals("Not Charging", DeviceText.powerText(health))
        assertEquals(Tone.Bad, DeviceText.batteryTone(health))
        assertEquals("0.8", DeviceText.memoryValue(health))
        assertEquals("Low", DeviceText.memoryNote(health))
        assertEquals(Tone.Warning, DeviceText.memoryTone(health))
        val plugged = DeviceHealth(batteryLevel = 100, charging = true, availableMemory = 2_400_000_000)
        assertEquals("Charged", DeviceText.powerText(plugged))
        assertEquals(Tone.Neutral, DeviceText.batteryTone(plugged))
        assertEquals("Free", DeviceText.memoryNote(plugged))
        val unknown = DeviceHealth()
        assertEquals("--", DeviceText.batteryValue(unknown))
        assertEquals("Unknown", DeviceText.powerText(unknown))
        assertEquals("--", DeviceText.memoryValue(unknown))
        assertNull(DeviceText.memoryNote(unknown))
    }
}
