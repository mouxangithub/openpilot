package io.zoompilot.jetlink.ui

import io.zoompilot.jetlink.device.DeviceHealth
import io.zoompilot.jetlink.server.Artifact
import io.zoompilot.jetlink.server.BenchReport
import io.zoompilot.jetlink.server.BenchStats
import io.zoompilot.jetlink.server.BenchWindow
import io.zoompilot.jetlink.server.Benchmark
import io.zoompilot.jetlink.server.CatalogInfo
import io.zoompilot.jetlink.server.Disk
import io.zoompilot.jetlink.server.Engine
import io.zoompilot.jetlink.server.HistorySample
import io.zoompilot.jetlink.server.Link
import io.zoompilot.jetlink.server.Medium
import io.zoompilot.jetlink.server.ModelRow
import io.zoompilot.jetlink.server.RowStatus
import io.zoompilot.jetlink.server.ServerInfo
import io.zoompilot.jetlink.server.Snapshot
import io.zoompilot.jetlink.server.Stages
import io.zoompilot.jetlink.server.Stats
import io.zoompilot.jetlink.server.Total
import kotlin.math.sin

/**
 * Sample state for previews and tests: copies of what a real server sends
 * (JetlinkKit's android_snapshot.json), with two minutes of history.
 */
object PreviewData {
    const val BIG_MODEL_SHA = "a086d5249fc308bb7c0ffbcbb2b8a53c3f6b1f0a1d2c3b4a5e6f7081920304050"
    const val CINQUE_SHA = "404a18cfd86d29630000000000000000000000000000000000000000000000ff"

    val stats = Stats(
        frames = 12_345,
        fps = 19.9,
        servedMs = Total(mean = 31.6, p99 = 38.4, max = 41.9),
        stagesMs = Stages(queue = 0.6, gpu = 29.4, other = 1.2, send = 0.4),
        slow = 0,
        windowS = 10.0,
    )

    /** Two minutes of one-second summaries, with one second over the budget. */
    val history: List<HistorySample> = (0 until 120).map { i ->
        val wobble = 3 * sin(i / 7.0)
        val spike = if (i == 83) 22.0 else 0.0
        HistorySample(
            at = 1_759_000_000.0 + i,
            stats = stats.copy(servedMs = Total(mean = 31.0 + wobble, p99 = 37.0 + wobble + spike, max = 40.0 + wobble + spike)),
        )
    }

    val loaded = ModelRow(
        id = BIG_MODEL_SHA,
        name = "BMRLNAP Model v4",
        displayName = "BMRLNAP Model v4",
        ref = "f877d7a0ccc3cce943c76e285214c020cd65c899",
        sha256 = BIG_MODEL_SHA,
        bytes = 765_953_504,
        buildTime = "2026-08-30T09:41:12Z",
        status = RowStatus(kind = "loaded"),
        preparedFor = listOf(Artifact(sha256 = BIG_MODEL_SHA, backend = "ort", device = "htp-SM8650", bytes = 800_000_000, current = true)),
        hasFiles = true,
        isLoaded = true,
        isRequestedByComma = true,
    )

    val downloading = ModelRow(
        id = CINQUE_SHA,
        name = "Cinque Terre Model V3",
        displayName = "Cinque Terre Model V3",
        ref = "37bfa1413edcdc2e8844984b83727c33f81d8f46",
        sha256 = CINQUE_SHA,
        bytes = 766_000_000,
        buildTime = "2026-09-17T11:04:00Z",
        status = RowStatus(kind = "downloading", frac = 0.42, rateBps = 41_000_000.0),
        isDefault = true,
    )

    val available = ModelRow(
        id = "b1",
        name = "North Nevada Model",
        displayName = "North Nevada Model",
        ref = "c0ffee",
        sha256 = "b1b2b3b4b5b6b7b8b9b0",
        bytes = 612_000_000,
        buildTime = "2026-07-02T08:00:00Z",
        status = RowStatus(kind = "not_downloaded"),
        canUse = true,
    )

    val orphan = ModelRow(
        id = "e0e1e2e3e4e5e6e7e8e9",
        sha256 = "e0e1e2e3e4e5e6e7e8e9",
        bytes = 700_000_000,
        status = RowStatus(kind = "prepared"),
        preparedFor = listOf(Artifact(current = true)),
        isOrphan = true,
        hasFiles = true,
        canUse = true,
    )

    val report = BenchReport(
        sha256 = BIG_MODEL_SHA,
        device = "htp-SM8650",
        seconds = 60.1,
        frames = 1195,
        frame = BenchStats(mean = 24.1, p50 = 23.8, p90 = 25.2, p99 = 27.9, max = 31.4),
        accelerator = BenchStats(mean = 21.9, p50 = 21.7, p90 = 22.8, p99 = 25.1, max = 28.2),
        over35 = 0,
        over50 = 0,
        windows = (0 until 6).map {
            BenchWindow(startSecond = it * 10, frame = BenchStats(mean = 24.0, p99 = 26.8 + it * 0.4, max = 29.0), thermal = if (it < 3) "nominal" else "fair")
        },
        thermalAtStart = "nominal",
        thermalAtEnd = "fair",
    )

    /** Serving the comma over USB 3 on the BMRLNAP model. */
    val serving = Snapshot(
        version = 10,
        running = true,
        port = 5599,
        server = ServerInfo(state = "serving", backend = "ort", runtimeVersion = "1.29.0", device = "htp-SM8650"),
        link = Link(state = "connected", peer = "usb", medium = "usb3"),
        medium = Medium(name = "usb3", title = "USB 3"),
        engine = Engine(state = "ready", sha256 = BIG_MODEL_SHA, frac = 1.0),
        recent = stats,
        history = history,
        models = listOf(downloading, loaded, available, orphan),
        catalog = CatalogInfo(fetchedAt = 1_759_000_000.0, defaultRef = "37bfa1413edcdc2e8844984b83727c33f81d8f46", count = 3),
        disk = Disk(modelsBytes = 765_953_504, enginesBytes = 800_000_000, freeBytes = 40_000_000_000),
        benchmark = Benchmark(state = "done", elapsed = 60.1, total = 60.0, frames = 1195, report = report, reportText = "Jetlink benchmark"),
    )

    val waiting = serving.copy(link = Link(state = "waiting"), medium = null, recent = null, history = emptyList())

    val preparing = waiting.copy(
        engine = Engine(state = "building", sha256 = CINQUE_SHA, stage = "compile", frac = 0.27),
        models = listOf(downloading.copy(status = RowStatus(kind = "preparing", stage = "compile", frac = 0.27)), available),
    )

    val empty = waiting.copy(engine = Engine(), models = listOf(downloading.copy(status = RowStatus(kind = "not_downloaded"), canUse = true), available))

    val health = DeviceHealth(
        thermal = "fair",
        headroom = 0.6f,
        batteryTemp = 34.2f,
        batteryLevel = 82,
        charging = true,
        availableMemory = 2_400_000_000,
    )
}
