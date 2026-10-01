package io.zoompilot.jetlink.server

import io.zoompilot.jetlink.ui.status.StatusState
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The snapshot the server hands over, parsed from the file the Swift side
 * pins it with (JetlinkKit's AppSnapshotTests write and check the same
 * file). A field the server renames fails here, not on a phone.
 */
class SnapshotTest {
    private val fixture = File(REPO, "JetlinkKit/Tests/JetlinkKitTests/Fixtures/android_snapshot.json")
    private val snapshot = Snapshot.parse(fixture.readText())

    @Test
    fun theServerAndLink() {
        assertTrue(snapshot.running)
        assertEquals(5599, snapshot.port)
        assertEquals("htp-SM8650", snapshot.server?.device)
        assertEquals("1.29.0", snapshot.server?.runtimeVersion)
        assertTrue(snapshot.connected)
        assertEquals("usb", snapshot.link.peer)
        assertEquals("USB 3", snapshot.medium?.title)
        assertFalse(snapshot.medium!!.slow)
    }

    @Test
    fun theEngineAndFrames() {
        assertEquals("ready", snapshot.engine.state)
        val recent = snapshot.recent!!
        assertEquals(38.4, recent.servedMs!!.p99, 1e-9)
        assertEquals(29.4, recent.stagesMs!!.gpu, 1e-9)
        assertEquals(1, snapshot.history.size)
        assertEquals(19.9, snapshot.history[0].stats.fps, 1e-9)
    }

    @Test
    fun theModelRows() {
        assertEquals(2, snapshot.models.size)
        val loaded = snapshot.row(snapshot.engine.sha256)!!
        assertTrue(loaded.isLoaded)
        assertTrue(loaded.isRequestedByComma)
        assertEquals("loaded", loaded.status.kind)
        assertTrue(loaded.isPrepared)
        assertTrue(loaded.hasFiles)
        assertEquals("BMRLNAP Model v4", snapshot.modelName(snapshot.engine.sha256))
        val downloading = snapshot.models.first { it.isDefault }
        assertEquals("downloading", downloading.status.kind)
        assertFalse(downloading.hasFiles)
        assertEquals(0.42, downloading.status.frac, 1e-9)
        assertEquals(41_000_000.0, downloading.status.rateBps, 1e-9)
        assertFalse(downloading.canUse)
        assertEquals(40_000_000_000L, snapshot.disk?.freeBytes)
    }

    @Test
    fun theBenchmark() {
        val benchmark = snapshot.benchmark!!
        assertEquals("done", benchmark.state)
        val report = benchmark.report!!
        assertEquals(27.9, report.frame.p99, 1e-9)
        assertEquals(0, report.over50)
        assertEquals(2, report.windows.size)
        assertEquals("fair", report.thermalAtEnd)
        assertTrue(benchmark.reportText!!.startsWith("Jetlink benchmark"))
    }

    @Test
    fun anEmptyStateParses() {
        val empty = Snapshot.parse("""{"version": 1, "running": false, "link": {"state": "waiting", "detail": "", "peer": null}}""")
        assertFalse(empty.running)
        assertFalse(empty.connected)
        assertNull(empty.recent)
        assertTrue(empty.models.isEmpty())
        assertEquals("none", empty.engine.state)
    }

    @Test
    fun theNotificationLine() {
        assertEquals("Connected over USB 3 · BMRLNAP Model v4", StatusState(RunState.Serving, snapshot).subtitle)
        assertEquals("Stopped", StatusState(RunState.Stopped, Snapshot()).subtitle)
    }

    companion object {
        /** The jetlink checkout: the tests run from android/app. */
        val REPO: File = generateSequence(File("").absoluteFile) { it.parentFile }
            .first { File(it, "JetlinkKit/Package.swift").exists() }
    }
}
