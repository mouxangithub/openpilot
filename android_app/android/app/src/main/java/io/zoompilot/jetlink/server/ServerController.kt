package io.zoompilot.jetlink.server

import android.content.Context
import android.net.Uri
import android.util.Log
import io.zoompilot.jetlink.settings.Chip
import io.zoompilot.jetlink.settings.SettingsValues
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.io.File

/** Whether the server runs, as the Status tab says it. */
sealed interface RunState {
    data object Stopped : RunState
    data object Starting : RunState
    data object Serving : RunState
    data class Failed(val reason: String) : RunState
}

/** A command's answer: ok, or the server's sentence why not. */
data class Reply(val ok: Boolean, val error: String?)

/**
 * The server in this process, and what the screens read from it: the
 * snapshot and the log. One for the life of the app; the foreground service
 * starts and stops it.
 */
class ServerController(private val context: Context, private val scope: CoroutineScope) {
    private val state = MutableStateFlow(Snapshot())
    val snapshot: StateFlow<Snapshot> = state.asStateFlow()

    private val run = MutableStateFlow<RunState>(RunState.Stopped)
    val runState: StateFlow<RunState> = run.asStateFlow()

    private val logLines = MutableStateFlow<List<String>>(emptyList())
    val logs: StateFlow<List<String>> = logLines.asStateFlow()

    private val lifecycle = Mutex()
    private var polling: Job? = null

    /** Where models and prepared engines live: app storage, never backed up. */
    val cacheDirectory: File get() = File(context.filesDir, "jetlink/cache")

    /** Starts the server with [settings], restarting one that runs. */
    suspend fun start(settings: SettingsValues) = lifecycle.withLock {
        if (!Native.loaded) {
            // a build without the Swift server: refuse in the UI, never crash
            run.value = RunState.Failed("libjetlink.so is missing from this build; rebuild it with the Swift server.")
            return@withLock
        }
        run.value = RunState.Starting
        // the server stops one that runs first
        val error = withContext(Dispatchers.IO) { Native.start(config(settings).toString()) }
        if (error != null) {
            Log.e(TAG, "the server did not start: $error")
            run.value = RunState.Failed(error)
            return@withLock
        }
        run.value = RunState.Serving
        if (polling?.isActive != true) {
            polling = scope.launch(Dispatchers.IO) { poll() }
        }
    }

    suspend fun stop() = lifecycle.withLock {
        if (Native.loaded) {
            withContext(Dispatchers.IO) { Native.stop() }
        }
        run.value = RunState.Stopped
    }

    private fun config(settings: SettingsValues): JsonObject = buildJsonObject {
        put("cache", cacheDirectory.absolutePath)
        put("device", settings.processor.id)
        put("keep_alive", settings.keepNpuAwake)
        put("keep_cpu_warm", settings.keepCpuAwake)
        put("port", settings.port)
        // bench tools reach the server over Wi-Fi or `adb forward`
        put("listen", true)
        put("usb", true)
        put("preload", true)
        put("chip", Chip.model)
        put("native_library_dir", context.applicationInfo.nativeLibraryDir)
    }

    /** Follows the snapshot and the log for as long as the app runs. */
    private suspend fun poll() {
        var logsAfter = 0L
        while (scope.isActive) {
            val text = Native.snapshot(state.value.version, SNAPSHOT_WAIT_MS)
            if (text.isNotEmpty()) {
                runCatching { Snapshot.parse(text) }
                    .onSuccess { state.value = it }
                    .onFailure { Log.w(TAG, "an unreadable snapshot: ${it.message}") }
            }
            val logs = runCatching { Snapshot.json.parseToJsonElement(Native.logs(logsAfter)).jsonObject }.getOrNull()
            if (logs != null) {
                val lines = (logs["lines"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { it.jsonPrimitive.contentOrNull }.orEmpty()
                logsAfter = logs["next"]?.jsonPrimitive?.contentOrNull?.toLongOrNull() ?: logsAfter
                if (lines.isNotEmpty()) {
                    // trimmed in chunks, not a copy of the whole log each second
                    val kept = logLines.value + lines
                    logLines.value = if (kept.size > LOG_LINES + LOG_LINES / 4) kept.takeLast(LOG_LINES) else kept
                }
            }
            if (run.value != RunState.Serving) delay(250)
        }
    }

    fun clearLogs() {
        logLines.value = emptyList()
    }

    /** One control command (docs/control-protocol.md); a refusal always says why. */
    suspend fun command(name: String, vararg arguments: Pair<String, Any?>): Reply = withContext(Dispatchers.IO) {
        val request = buildJsonObject {
            put("cmd", name)
            for ((key, value) in arguments) {
                when (value) {
                    null -> {}
                    is String -> put(key, value)
                    is Number -> put(key, value)
                    is Boolean -> put(key, value)
                    else -> put(key, value.toString())
                }
            }
        }
        val reply = runCatching { Snapshot.json.parseToJsonElement(Native.command(request.toString())).jsonObject }
            .getOrElse { buildJsonObject { put("ok", false); put("error", it.message ?: "no reply") } }
        val ok = reply["ok"]?.jsonPrimitive?.booleanOrNull == true
        val error = (reply["error"] as? JsonPrimitive)?.contentOrNull
        Reply(ok, if (ok) error else error ?: "The $name command failed.")
    }

    suspend fun refreshCatalog() = command("catalog", "refresh" to true)
    /** Prepares and loads a model at the frame skip a comma asks for, the server's default. */
    suspend fun use(sha256: String) = command("prepare", "sha256" to sha256)
    suspend fun download(ref: String?, sha256: String?) = command("download", "ref" to ref, "sha256" to sha256)
    suspend fun cancelDownload(sha256: String) = command("cancel_download", "sha256" to sha256)
    suspend fun unload() = command("unload")
    suspend fun forget(sha256: String, artifacts: Boolean, model: Boolean) =
        command("forget", "sha256" to sha256, "artifacts" to artifacts, "model" to model)
    suspend fun importModel(path: String) = command("import", "path" to path)

    /**
     * Imports an .onnx the person picked (Android's document picker hands over a
     * content URI, not a path): copied into the app's cache first, then imported
     * by the server as a file, and the copy deleted once the import is done.
     */
    suspend fun importModel(uri: Uri): Reply = withContext(Dispatchers.IO) {
        val staging = File(context.cacheDir, "import").apply { mkdirs() }
        val name = uri.lastPathSegment?.substringAfterLast('/')?.takeIf { it.endsWith(".onnx") } ?: "model.onnx"
        val copy = File(staging, name)
        val copied = runCatching {
            context.contentResolver.openInputStream(uri)?.use { input -> copy.outputStream().use { input.copyTo(it, 1 shl 20) } }
        }.getOrNull()
        if (copied == null) {
            return@withContext Reply(false, "Couldn't read that file.")
        }
        val reply = importModel(copy.absolutePath)
        if (!reply.ok) {
            copy.delete()
        } else {
            // the server copies it into the cache; drop ours when it says done
            scope.launch {
                snapshot.first { snap -> snap.imports.any { it.path == copy.absolutePath && (it.state == "done" || it.state == "failed") } }
                copy.delete()
            }
        }
        reply
    }
    suspend fun benchmark(seconds: Int) = command("benchmark", "seconds" to seconds)
    suspend fun cancelBenchmark() = command("cancel_benchmark")

    /** The onnxruntime version, for Settings. */
    fun runtimeVersion(): String? = runCatching { Native.runtimeVersion() }.getOrNull()

    companion object {
        private const val TAG = "jetlink"
        /** The longest a snapshot waits for news; the headline refreshes at least this often. */
        const val SNAPSHOT_WAIT_MS = 1000
        const val LOG_LINES = 5000
    }
}
