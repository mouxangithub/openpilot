package io.zoompilot.jetlink.ui.models

import io.zoompilot.jetlink.server.ImportState
import io.zoompilot.jetlink.server.ModelRow
import io.zoompilot.jetlink.server.Snapshot
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.Tone

/** The one control on a model's row, as a store has one per app. */
enum class RowAction {
    /** Nothing to press: the catalog is still resolving it. */
    None,
    Get,
    Use,
    Retry,

    /** A download ring, a tap stops it. */
    Stop,

    /** A preparing ring. */
    Preparing,

    /** In use: a check, with Stop Using behind it. */
    InUse,
}

/** How a model row reads and what it offers, the same as the iPhone's list. */
object ModelRules {
    /** One line of facts or progress under the name. */
    fun subtitle(row: ModelRow): String {
        val status = row.status
        return when (status.kind) {
            "downloading" -> {
                val percent = Format.percent(status.frac)
                if (status.rateBps > 0) "Downloading · $percent · ${Format.rate(status.rateBps)}" else "Downloading · $percent"
            }
            "preparing" -> "${Format.stageName(status.stage)} · ${Format.percent(status.frac)}"
            "loaded" -> if (row.isOrphan) "In Use · ${row.sha256.orEmpty().take(12)}" else "In Use"
            "failed" -> "Failed"
            "unresolved" -> "Checking…"
            else -> buildList {
                if (row.isOrphan) row.sha256?.let { add(it.take(12)) }
                row.bytes?.let { add(Format.bytes(it)) }
                Format.buildDate(row.buildTime).takeIf { it.isNotEmpty() }?.let(::add)
                if (status.kind == "prepared" || row.isPrepared) add("Ready")
            }.joinToString(" · ")
        }
    }

    fun subtitleTone(row: ModelRow): Tone = when (row.status.kind) {
        "loaded" -> Tone.Good
        "failed" -> Tone.Bad
        else -> Tone.Neutral
    }

    /** What went wrong, under a failed row; the rest is in Logs. */
    fun failure(row: ModelRow): String? =
        if (row.status.kind == "failed") (row.status.detail ?: row.status.msg)?.takeIf { it.isNotBlank() }?.let(Format::sentence) else null

    fun action(row: ModelRow): RowAction = when (row.status.kind) {
        "loaded" -> RowAction.InUse
        "downloading" -> RowAction.Stop
        "preparing" -> RowAction.Preparing
        "unresolved" -> RowAction.None
        "not_downloaded" -> RowAction.Get
        "failed" -> RowAction.Retry
        else -> RowAction.Use
    }

    /**
     * True when using this model would interrupt the comma that is driving:
     * a comma is connected and a different model is in use or being prepared.
     */
    fun useNeedsConfirmation(snapshot: Snapshot, row: ModelRow): Boolean {
        if (!snapshot.connected) return false
        val inFlight = snapshot.engine.sha256 ?: return false
        if (snapshot.engine.state == "none") return false
        return inFlight != row.sha256
    }

    /** The catalog's models, the ones added from a file, and the ones a comma sent. */
    data class Sections(val available: List<ModelRow>, val added: List<ModelRow>, val uploaded: List<ModelRow>)

    fun sections(models: List<ModelRow>): Sections = Sections(
        available = models.filter { !it.isLocal && !it.isOrphan },
        added = models.filter { it.isLocal && !it.isOrphan },
        uploaded = models.filter { it.isOrphan },
    )

    /** "766 MB Downloaded · 800 MB Prepared · 40 GB Free". */
    fun diskLine(snapshot: Snapshot): String? {
        val disk = snapshot.disk ?: return null
        return listOfNotNull(
            "${Format.bytes(disk.modelsBytes)} Downloaded",
            "${Format.bytes(disk.enginesBytes)} Prepared",
            disk.freeBytes?.let { "${Format.bytes(it)} Free" },
        ).joinToString(" · ")
    }

    /** Imports still running, or failed, for the Adding section. */
    fun activeImports(imports: List<ImportState>): List<ImportState> = imports.filter { it.state != "done" }

    /** "Checking · 42%" while hashing, "Copying · 42%" while copying. */
    fun importLine(import: ImportState): String = when (import.state) {
        "hashing" -> "Checking · ${Format.percent(import.frac)}"
        "copying" -> "Copying · ${Format.percent(import.frac)}"
        "failed" -> "Failed"
        else -> "Adding"
    }
}
