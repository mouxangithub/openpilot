package io.zoompilot.jetlink.ui

import io.zoompilot.jetlink.server.HistorySample
import io.zoompilot.jetlink.server.Stats
import io.zoompilot.jetlink.server.Total
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import java.time.ZoneOffset
import java.util.Locale

/** The numbers and words every screen shares, pinned to what the iPhone app shows. */
class FormatTest {
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
    fun roomAgainstTheBudget() {
        assertEquals(Room.Plenty, Room.forP99(31.6))
        assertEquals(Room.Plenty, Room.forP99(40.0))
        assertEquals(Room.Tight, Room.forP99(40.1))
        assertEquals(Room.Tight, Room.forP99(50.0))
        assertEquals(Room.Over, Room.forP99(50.1))
        assertEquals("Over Budget", Room.Over.title)
    }

    @Test
    fun theVerdict() {
        assertEquals(Verdict.Good, Verdict.of(35.0))
        assertEquals(Verdict.Tight, Verdict.of(35.0, over50 = 1))
        assertEquals(Verdict.Tight, Verdict.of(35.1))
        assertEquals(Verdict.Tight, Verdict.of(50.0))
        assertEquals(Verdict.Slow, Verdict.of(50.1))
        assertEquals("Fast Enough", Verdict.Good.title)
        assertEquals("Too Slow", Verdict.Slow.title)
    }

    @Test
    fun headroom() {
        assertEquals("18.4 ms headroom", Format.headroomText(31.6))
        assertEquals("0.0 ms headroom", Format.headroomText(50.0))
        assertEquals("3.2 ms over", Format.headroomText(53.2))
    }

    @Test
    fun thermalWords() {
        assertEquals("Normal", Thermal.of("nominal").title)
        assertEquals("Warm", Thermal.of("fair").title)
        assertEquals("Hot", Thermal.of("serious").title)
        assertEquals("Critical", Thermal.of("critical").title)
        // an unknown or missing word reads as fair, as on the iPhone
        assertEquals(Thermal.Fair, Thermal.of(""))
        assertNull(Thermal.Fair.note)
        assertEquals("Throttling", Thermal.Serious.note)
    }

    @Test
    fun stageNames() {
        assertEquals("Compiling", Format.stageName("compile"))
        assertEquals("Loading", Format.stageName("load"))
        assertEquals("Working", Format.stageName(null))
        assertEquals("Working", Format.stageName("something new"))
    }

    @Test
    fun bytesAsTheFinderWritesThem() {
        assertEquals("766 MB", Format.bytes(765_953_504))
        assertEquals("1.8 GB", Format.bytes(1_800_000_000))
        assertEquals("40 GB", Format.bytes(40_000_000_000))
        assertEquals("800 MB", Format.bytes(800_000_000))
        assertEquals("999 bytes", Format.bytes(999))
        assertEquals("1 MB", Format.bytes(999_950))
        assertEquals("41 MB/s", Format.rate(41_000_000.0))
        assertEquals("0 bytes/s", Format.rate(Double.NaN))
    }

    @Test
    fun clockAndPercent() {
        assertEquals("1:00", Format.clock(60.1))
        assertEquals("10:00", Format.clock(600.0))
        assertEquals("0:09", Format.clock(9.99))
        assertEquals("42%", Format.percent(0.42))
        assertEquals("100%", Format.percent(1.3))
        assertEquals("12,345", Format.integer(12_345))
    }

    @Test
    fun buildDates() {
        assertEquals("Aug 30, 2026", Format.buildDate("2026-08-30T09:41:12Z", ZoneOffset.UTC, Locale.US))
        assertEquals("Sep 17, 2026", Format.buildDate("2026-09-17T11:04:00.250Z", ZoneOffset.UTC, Locale.US))
        assertEquals("", Format.buildDate(null))
        assertEquals("", Format.buildDate("not a date"))
    }

    @Test
    fun sentences() {
        assertEquals("Another app holds the comma's interface.", Format.sentence("another app holds the comma's interface"))
        assertEquals("Done!", Format.sentence("Done!"))
        assertEquals("", Format.sentence("  "))
    }

    @Test
    fun logLevels() {
        assertEquals(LogLevel.Warning, Format.logLevel("2026-09-27 12:53:24,982 WARNING jetlink.x: msg"))
        assertEquals(LogLevel.Error, Format.logLevel("2026-09-27 12:53:24,982 ERROR   jetlink.x: msg"))
        assertEquals(LogLevel.Info, Format.logLevel("2026-09-27 12:53:24,982 INFO    jetlink.x: an ERROR: in the message"))
    }

    @Test
    fun historyInFiveSecondBuckets() {
        fun sample(at: Double, p99: Double, max: Double) = HistorySample(at, Stats(servedMs = Total(mean = 30.0, p99 = p99, max = max)))
        val history = listOf(
            sample(100.0, 30.0, 32.0),
            sample(101.0, 44.0, 61.0),
            sample(105.0, 33.0, 35.0),
            sample(109.0, 31.0, 34.0),
        )
        val buckets = Format.historyBuckets(history)
        // oldest first: 100 and 101 are 8 and 9 s old, bucket 1; 105 and 109 bucket 0
        assertEquals(listOf(1, 0), buckets.map { it.index })
        assertEquals(44.0, buckets[0].p99, 1e-9)
        assertEquals(61.0, buckets[0].max, 1e-9)
        assertEquals(33.0, buckets[1].p99, 1e-9)
        assertEquals(5.0, buckets[0].age, 1e-9)
        assertEquals(emptyList<HistoryBucket>(), Format.historyBuckets(emptyList()))
    }

    @Test
    fun historyDropsWhatIsOlderThanTwoMinutes() {
        val history = (0..200).map { HistorySample(it.toDouble(), Stats(servedMs = Total(p99 = 30.0, max = 31.0))) }
        val buckets = Format.historyBuckets(history)
        assertEquals(25, buckets.size)
        assertEquals(120.0, buckets.first().age, 1e-9)
    }
}
