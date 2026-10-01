package io.zoompilot.jetlink.ui.models

import io.zoompilot.jetlink.server.Disk
import io.zoompilot.jetlink.server.Engine
import io.zoompilot.jetlink.server.ImportState
import io.zoompilot.jetlink.server.Link
import io.zoompilot.jetlink.server.RowStatus
import io.zoompilot.jetlink.ui.PreviewData
import io.zoompilot.jetlink.ui.Tone
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.Locale
import java.util.TimeZone

/** A Models row's line, button and confirmations, as the iPhone's list has them. */
class ModelRulesTest {
    private lateinit var locale: Locale
    private lateinit var zone: TimeZone

    @Before
    fun englishDates() {
        locale = Locale.getDefault()
        zone = TimeZone.getDefault()
        Locale.setDefault(Locale.US)
        TimeZone.setDefault(TimeZone.getTimeZone("UTC"))
    }

    @After
    fun restore() {
        Locale.setDefault(locale)
        TimeZone.setDefault(zone)
    }

    @Test
    fun subtitles() {
        assertEquals("Downloading · 42% · 41 MB/s", ModelRules.subtitle(PreviewData.downloading))
        assertEquals("Downloading · 42%", ModelRules.subtitle(PreviewData.downloading.copy(status = RowStatus("downloading", frac = 0.42))))
        assertEquals("Compiling · 27%", ModelRules.subtitle(PreviewData.downloading.copy(status = RowStatus("preparing", frac = 0.27, stage = "compile"))))
        assertEquals("In Use", ModelRules.subtitle(PreviewData.loaded))
        assertEquals("612 MB · Jul 2, 2026", ModelRules.subtitle(PreviewData.available))
        assertEquals("e0e1e2e3e4e5 · 700 MB · Ready", ModelRules.subtitle(PreviewData.orphan))
        assertEquals("Failed", ModelRules.subtitle(PreviewData.available.copy(status = RowStatus("failed", detail = "the model could not be parsed"))))
        assertEquals("Checking…", ModelRules.subtitle(PreviewData.available.copy(status = RowStatus("unresolved"))))
    }

    @Test
    fun tonesAndFailures() {
        assertEquals(Tone.Good, ModelRules.subtitleTone(PreviewData.loaded))
        val failed = PreviewData.available.copy(status = RowStatus("failed", detail = "the model could not be parsed"))
        assertEquals(Tone.Bad, ModelRules.subtitleTone(failed))
        assertEquals("The model could not be parsed.", ModelRules.failure(failed))
        assertNull(ModelRules.failure(PreviewData.available))
    }

    @Test
    fun titles() {
        assertEquals("Uploaded Model", PreviewData.orphan.title)
        assertEquals("BMRLNAP Model v4", PreviewData.loaded.title)
    }

    @Test
    fun oneButtonPerRow() {
        assertEquals(RowAction.Get, ModelRules.action(PreviewData.available))
        assertEquals(RowAction.Use, ModelRules.action(PreviewData.orphan))
        assertEquals(RowAction.Stop, ModelRules.action(PreviewData.downloading))
        assertEquals(RowAction.InUse, ModelRules.action(PreviewData.loaded))
        assertEquals(RowAction.Retry, ModelRules.action(PreviewData.available.copy(status = RowStatus("failed"))))
        assertEquals(RowAction.Preparing, ModelRules.action(PreviewData.available.copy(status = RowStatus("preparing"))))
        assertEquals(RowAction.None, ModelRules.action(PreviewData.available.copy(status = RowStatus("unresolved"))))
    }

    @Test
    fun switchingWhileTheCommaDrivesAsksFirst() {
        val serving = PreviewData.serving
        assertTrue(ModelRules.useNeedsConfirmation(serving, PreviewData.available))
        assertFalse(ModelRules.useNeedsConfirmation(serving, PreviewData.loaded))
        assertFalse(ModelRules.useNeedsConfirmation(serving.copy(link = Link(state = "waiting")), PreviewData.available))
        assertFalse(ModelRules.useNeedsConfirmation(serving.copy(engine = Engine()), PreviewData.available))
    }

    @Test
    fun sectionsAndDisk() {
        val sections = ModelRules.sections(PreviewData.serving.models)
        assertEquals(3, sections.available.size)
        assertEquals(0, sections.added.size)
        assertEquals(listOf(PreviewData.orphan), sections.uploaded)
        assertEquals("766 MB Downloaded · 800 MB Prepared · 40 GB Free", ModelRules.diskLine(PreviewData.serving))
        assertEquals("1 GB Downloaded · 0 bytes Prepared", ModelRules.diskLine(PreviewData.serving.copy(disk = Disk(1_000_000_000, 0, null))))
    }

    @Test
    fun imports() {
        val hashing = ImportState(path = "/cache/import/model.onnx", state = "hashing", frac = 0.5)
        val done = hashing.copy(state = "done")
        assertEquals(listOf(hashing), ModelRules.activeImports(listOf(hashing, done)))
        assertEquals("Checking · 50%", ModelRules.importLine(hashing))
        assertEquals("Copying · 50%", ModelRules.importLine(hashing.copy(state = "copying")))
    }
}
