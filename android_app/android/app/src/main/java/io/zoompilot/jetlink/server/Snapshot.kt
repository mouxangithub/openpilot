package io.zoompilot.jetlink.server

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNamingStrategy

/**
 * Everything the screens show, as the server's AppSnapshot hands it over
 * (JetlinkKit/Sources/JetlinkKit/AppSnapshot.swift): the control protocol's
 * events, and the Models rows the other apps build the same way. Field names
 * are the protocol's snake_case; JetlinkKit's
 * Tests/JetlinkKitTests/Fixtures/android_snapshot.json is one, and the unit
 * tests parse it.
 */
@Serializable
data class Snapshot(
    val version: Long = 0,
    val running: Boolean = false,
    val port: Int? = null,
    val server: ServerInfo? = null,
    val link: Link = Link(),
    val medium: Medium? = null,
    val engine: Engine = Engine(),
    /** The last ten seconds of frames, while a comma is connected. */
    val recent: Stats? = null,
    /** One summary a second, for the history chart. */
    val history: List<HistorySample> = emptyList(),
    val models: List<ModelRow> = emptyList(),
    val catalog: CatalogInfo? = null,
    val disk: Disk? = null,
    val imports: List<ImportState> = emptyList(),
    val benchmark: Benchmark? = null,
    val shutdownRequests: Int = 0,
) {
    val connected: Boolean get() = link.state == "connected"

    fun row(sha256: String?): ModelRow? = sha256?.let { sha -> models.firstOrNull { it.sha256 == sha } }

    /** The engine's model by name. */
    fun modelName(sha256: String?): String? = row(sha256)?.title

    companion object {
        @OptIn(ExperimentalSerializationApi::class)
        val json = Json {
            ignoreUnknownKeys = true
            coerceInputValues = true
            explicitNulls = false
            namingStrategy = JsonNamingStrategy.SnakeCase
        }

        fun parse(text: String): Snapshot = json.decodeFromString(serializer(), text)
    }
}

@Serializable
data class ServerInfo(
    val state: String = "",
    val detail: String = "",
    val backend: String? = null,
    val runtimeVersion: String? = null,
    val device: String? = null,
)

@Serializable
data class Link(
    /** "waiting", "connected" or "disconnected". */
    val state: String = "waiting",
    val detail: String = "",
    val peer: String? = null,
    val medium: String? = null,
)

/** What the comma's link is carried over: "USB 3", and whether that is too slow. */
@Serializable
data class Medium(
    val name: String = "usb",
    val title: String = "USB",
    val slow: Boolean = false,
)

@Serializable
data class Engine(
    /** "none", "building", "loading", "ready" or "failed". */
    val state: String = "none",
    val sha256: String? = null,
    val detail: String = "",
    val stage: String? = null,
    val frac: Double = 0.0,
    val msg: String = "",
    val loadOnly: Boolean = false,
)

@Serializable
data class Stats(
    val frames: Long = 0,
    val fps: Double = 0.0,
    val servedMs: Total? = null,
    val stagesMs: Stages? = null,
    val slow: Int = 0,
    val windowS: Double = 0.0,
)

@Serializable
data class Total(val mean: Double = 0.0, val p99: Double = 0.0, val max: Double = 0.0)

/** Means that add up to the served mean: staging the inputs, the model, the rest, the send. */
@Serializable
data class Stages(val queue: Double = 0.0, val gpu: Double = 0.0, val other: Double = 0.0, val send: Double = 0.0)

@Serializable
data class HistorySample(val at: Double = 0.0, val stats: Stats = Stats())

@Serializable
data class ModelRow(
    val id: String,
    val name: String = "",
    val displayName: String = "",
    val ref: String? = null,
    val sha256: String? = null,
    val bytes: Long? = null,
    val buildTime: String? = null,
    val status: RowStatus = RowStatus(),
    val preparedFor: List<Artifact> = emptyList(),
    val isLoaded: Boolean = false,
    val isDefault: Boolean = false,
    val isRequestedByComma: Boolean = false,
    val isLocal: Boolean = false,
    val isOrphan: Boolean = false,
    val canUse: Boolean = false,
    /** Something on the phone to delete: the model, or an engine prepared from it. */
    val hasFiles: Boolean = false,
) {
    /** Prepared for this phone's processor, and so quick to load. */
    val isPrepared: Boolean get() = preparedFor.any { it.current }

    /** Its name; "Uploaded Model" for one no catalog names. */
    val title: String get() = if (isOrphan) "Uploaded Model" else displayName
}

@Serializable
data class RowStatus(
    /** unresolved, not_downloaded, downloading, downloaded, preparing, prepared, loaded, failed */
    val kind: String = "not_downloaded",
    val frac: Double = 0.0,
    val rateBps: Double = 0.0,
    val stage: String? = null,
    val msg: String? = null,
    val detail: String? = null,
)

@Serializable
data class Artifact(
    val sha256: String = "",
    val key: String = "",
    val path: String = "",
    val bytes: Long = 0,
    val backend: String = "",
    val runtimeVersion: String = "",
    val device: String = "",
    val builtAt: String? = null,
    val buildSeconds: Double? = null,
    val checkpoint: String? = null,
    val current: Boolean = false,
)

@Serializable
data class CatalogInfo(
    val fetchedAt: Double? = null,
    val error: String? = null,
    val defaultRef: String = "",
    val count: Int = 0,
)

@Serializable
data class Disk(val modelsBytes: Long = 0, val enginesBytes: Long = 0, val freeBytes: Long? = null)

@Serializable
data class ImportState(
    val path: String = "",
    /** "hashing", "copying", "done" or "failed". */
    val state: String = "",
    val frac: Double = 0.0,
    val sha256: String? = null,
    val detail: String = "",
)

@Serializable
data class Benchmark(
    /** "running", "done", "cancelled" or "failed". */
    val state: String = "",
    val elapsed: Double = 0.0,
    val total: Double = 0.0,
    val frames: Int = 0,
    val frame: BenchStats? = null,
    val report: BenchReport? = null,
    val detail: String = "",
    /** The report as the other apps share it. */
    val reportText: String? = null,
)

@Serializable
data class BenchStats(
    val mean: Double = 0.0,
    val p50: Double = 0.0,
    val p90: Double = 0.0,
    val p99: Double = 0.0,
    val max: Double = 0.0,
)

@Serializable
data class BenchReport(
    val sha256: String = "",
    val device: String = "",
    val seconds: Double = 0.0,
    val frames: Int = 0,
    val frame: BenchStats = BenchStats(),
    val accelerator: BenchStats = BenchStats(),
    val queues: BenchStats = BenchStats(),
    val output: BenchStats = BenchStats(),
    val build: String = "",
    val over35: Int = 0,
    val over50: Int = 0,
    val windows: List<BenchWindow> = emptyList(),
    val thermalAtStart: String = "",
    val thermalAtEnd: String = "",
    val cancelled: Boolean = false,
)

@Serializable
data class BenchWindow(val startSecond: Int = 0, val frame: BenchStats = BenchStats(), val thermal: String = "")
