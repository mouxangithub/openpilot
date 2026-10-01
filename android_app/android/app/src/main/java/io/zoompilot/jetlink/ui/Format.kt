package io.zoompilot.jetlink.ui

import io.zoompilot.jetlink.server.HistorySample
import io.zoompilot.jetlink.server.Stages
import java.text.NumberFormat
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/** The 50 ms the comma gives each frame at 20 Hz. */
const val BUDGET_MS = 50.0

/** Less room than this at P99 reads as tight: the comma's own work and the cable come out of the same 50 ms. */
const val TIGHT_MS = 10.0

/** A P99 at or under this, with no frame over the budget, leaves room for the cable. */
const val ROOMY_P99_MS = 35.0

/** The seconds of history the Status tab charts. */
const val HISTORY_SECONDS = 120

/** What a state means, as a colour: the same five everywhere. */
enum class Tone { Neutral, Info, Good, Warning, Bad }

/** The room left in the frame budget at P99. */
enum class Room(val title: String, val tone: Tone) {
    Plenty("Good", Tone.Good),
    Tight("Tight", Tone.Warning),
    Over("Over Budget", Tone.Bad);

    companion object {
        fun of(headroomMs: Double): Room = when {
            headroomMs < 0 -> Over
            headroomMs < TIGHT_MS -> Tight
            else -> Plenty
        }

        fun forP99(p99: Double): Room = of(BUDGET_MS - p99)
    }
}

/** Fast enough, tight, or too slow: the benchmark's answer, as on the iPhone and the Mac. */
enum class Verdict(val title: String, val detail: String, val tone: Tone) {
    Good("Fast Enough", "Room for the cable in the 50 ms budget.", Tone.Good),
    Tight("Tight", "Little room left for the cable.", Tone.Warning),
    Slow("Too Slow", "Misses 20 frames a second.", Tone.Bad);

    companion object {
        fun of(p99: Double, over50: Int = 0): Verdict = when {
            p99 <= ROOMY_P99_MS && over50 == 0 -> Good
            p99 <= BUDGET_MS -> Tight
            else -> Slow
        }
    }
}

/** How warm the phone is, from the word the server and DeviceMonitor use. */
enum class Thermal(val title: String, val tone: Tone) {
    Nominal("Normal", Tone.Neutral),
    Fair("Warm", Tone.Neutral),
    Serious("Hot", Tone.Warning),
    Critical("Critical", Tone.Bad);

    /** Said only when the heat costs frames. */
    val note: String? get() = if (this == Serious || this == Critical) "Throttling" else null

    companion object {
        /** nominal, fair, serious or critical; anything else reads as fair, as on the iPhone. */
        fun of(label: String): Thermal = when (label) {
            "nominal" -> Nominal
            "serious" -> Serious
            "critical" -> Critical
            else -> Fair
        }
    }
}

/** The four places a frame's time goes, in the order they happen. */
enum class FrameStage(val title: String) {
    Input("Input"),
    Model("Model"),
    Other("Other"),
    Send("Send");

    fun value(stages: Stages): Double = when (this) {
        Input -> stages.queue
        Model -> stages.gpu
        Other -> stages.other
        Send -> stages.send
    }
}

/** A log line's level, from "time LEVEL name: message". */
enum class LogLevel { Info, Warning, Error }

/** Five seconds of history: the worst P99 and the worst frame in it. */
data class HistoryBucket(val index: Int, val age: Double, val p99: Double, val max: Double)

object Format {
    /** "18.4": one decimal, in the phone's locale. */
    fun decimal(value: Double): String = String.format(Locale.getDefault(), "%.1f", value)

    /** "18.4 ms". */
    fun ms(value: Double): String = "${decimal(value)} ms"

    /** "12,345". */
    fun integer(value: Long): String = NumberFormat.getIntegerInstance(Locale.getDefault()).format(value)

    fun integer(value: Int): String = integer(value.toLong())

    /** "42%", clamped to 0 to 100. */
    fun percent(frac: Double): String = "${(frac.coerceIn(0.0, 1.0) * 100).roundToInt()}%"

    /** "18.4 ms headroom", or "3.2 ms over" once P99 is past the budget. */
    fun headroomText(p99: Double): String {
        val room = BUDGET_MS - p99
        return if (room >= 0) "${ms(room)} headroom" else "${ms(-room)} over"
    }

    /** The server's stage names in plain English. */
    fun stageName(stage: String?): String = when (stage) {
        "upload" -> "Receiving"
        "patch" -> "Preparing"
        "parse" -> "Reading"
        "convert" -> "Converting"
        "compile" -> "Compiling"
        "build" -> "Building"
        "save" -> "Saving"
        "load" -> "Loading"
        "failed" -> "Failed"
        else -> "Working"
    }

    /**
     * "766 MB", "1.8 GB": decimal units, one decimal at most, and none on a
     * whole number of units, as the Finder writes them.
     */
    fun bytes(count: Long): String {
        val units = listOf("bytes", "KB", "MB", "GB", "TB", "PB")
        var value = count.toDouble()
        var unit = 0
        while (abs(value) >= 1000 && unit < units.size - 1) {
            value /= 1000
            unit++
        }
        if (unit == 0) return "$count bytes"
        var rounded = (value * 10).roundToLong() / 10.0
        if (abs(rounded) >= 1000 && unit < units.size - 1) {
            rounded = ((rounded / 1000) * 10).roundToLong() / 10.0
            unit++
        }
        val text = if (rounded == Math.rint(rounded)) {
            rounded.roundToLong().toString()
        } else {
            String.format(Locale.getDefault(), "%.1f", rounded)
        }
        return "$text ${units[unit]}"
    }

    /** "41 MB/s". */
    fun rate(bytesPerSecond: Double): String {
        val clamped = if (bytesPerSecond.isFinite() && bytesPerSecond > 0) bytesPerSecond else 0.0
        return bytes(clamped.roundToLong()) + "/s"
    }

    /** "2.4": gigabytes, for a tile with its unit beside it. */
    fun gigabytes(count: Long): String = decimal(count / 1e9)

    /** "1:00" for 60 seconds. */
    fun clock(seconds: Double): String {
        val whole = seconds.toLong().coerceAtLeast(0)
        return "${whole / 60}:${(whole % 60).toString().padStart(2, '0')}"
    }

    /** "Aug 30, 2026" from the catalog's ISO-8601 build time; empty when there is none. */
    fun buildDate(iso: String?, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String {
        if (iso.isNullOrBlank()) return ""
        val instant = runCatching { OffsetDateTime.parse(iso).toInstant() }.getOrNull() ?: return ""
        return mediumDate.withLocale(locale).format(instant.atZone(zone))
    }

    private val mediumDate: DateTimeFormatter = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)

    /** A sentence from the server or Android, capitalised and closed with a full stop. */
    fun sentence(text: String): String {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return trimmed
        val capital = trimmed.replaceFirstChar { it.uppercaseChar() }
        return if (capital.last() in ".!?") capital else "$capital."
    }

    /** Errors red, warnings orange: the Python server pads the level, so a warning is " WARNING" and an error " ERROR ". */
    fun logLevel(line: String): LogLevel = when {
        line.contains(" ERROR ") -> LogLevel.Error
        line.contains(" WARNING") -> LogLevel.Warning
        else -> LogLevel.Info
    }

    /** Five-second buckets of the last two minutes, oldest first, each the worst of its seconds. */
    fun historyBuckets(history: List<HistorySample>, bucketSeconds: Double = 5.0): List<HistoryBucket> {
        val latest = history.lastOrNull()?.at ?: return emptyList()
        val p99 = HashMap<Int, Double>()
        val max = HashMap<Int, Double>()
        for (sample in history) {
            val age = latest - sample.at
            if (age < 0 || age > HISTORY_SECONDS) continue
            val index = (age / bucketSeconds).toInt()
            val served = sample.stats.servedMs ?: continue
            p99[index] = maxOf(p99[index] ?: 0.0, served.p99)
            max[index] = maxOf(max[index] ?: 0.0, served.max)
        }
        return p99.keys.sortedDescending().map { HistoryBucket(it, it * bucketSeconds, p99.getValue(it), max.getValue(it)) }
    }
}
