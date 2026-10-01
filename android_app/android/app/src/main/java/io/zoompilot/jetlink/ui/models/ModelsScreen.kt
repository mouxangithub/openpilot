package io.zoompilot.jetlink.ui.models

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.zoompilot.jetlink.AppGraph
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.server.ImportState
import io.zoompilot.jetlink.server.ModelRow
import io.zoompilot.jetlink.server.Reply
import io.zoompilot.jetlink.server.Snapshot
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.PreviewData
import io.zoompilot.jetlink.ui.components.CardSpacing
import io.zoompilot.jetlink.ui.components.FormSection
import io.zoompilot.jetlink.ui.components.ProgressRing
import io.zoompilot.jetlink.ui.components.ReadableWidth
import io.zoompilot.jetlink.ui.components.RowDivider
import io.zoompilot.jetlink.ui.components.Tag
import kotlinx.coroutines.launch

/**
 * Use Model, in one step: the server downloads the model when it is not on
 * disk, prepares it when it has no engine, and loads it. A row the catalog
 * has not resolved to a checksum yet is downloaded by its ref.
 */
suspend fun useModel(graph: AppGraph, row: ModelRow): Reply? {
    val sha = row.sha256
    val ref = row.ref
    return if (sha != null) graph.server.use(sha) else if (ref != null) graph.server.download(ref, null) else null
}

/** What a row's buttons do, handed down from the screen. */
class ModelActions(
    val use: (ModelRow) -> Unit = {},
    val cancel: (ModelRow) -> Unit = {},
    val unload: () -> Unit = {},
    val delete: (ModelRow) -> Unit = {},
    val refresh: () -> Unit = {},
)

private sealed interface Confirmation {
    val row: ModelRow

    data class Delete(override val row: ModelRow) : Confirmation
    data class Switch(override val row: ModelRow) : Confirmation
}

/**
 * The catalog and what is on this phone. One button per model: Get
 * downloads, prepares and loads it; Use loads one that is here; a ring shows
 * a download, and a tap on it stops it.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModelsScreen(graph: AppGraph) {
    val snapshot by graph.server.snapshot.collectAsStateWithLifecycle()
    var error by remember { mutableStateOf<String?>(null) }
    var confirmation by remember { mutableStateOf<Confirmation?>(null) }
    var refreshing by remember { mutableStateOf(false) }
    /** Runs a command off the main thread; a refusal shows in a dialog. */
    val run = { command: suspend () -> Reply? ->
        graph.scope.launch {
            val reply = command()
            if (reply != null && !reply.ok) error = reply.error
        }
        Unit
    }
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) run { graph.server.importModel(uri) }
    }
    val refresh = {
        refreshing = true
        run {
            try {
                graph.server.refreshCatalog()
            } finally {
                refreshing = false
            }
        }
    }
    val actions = ModelActions(
        use = { row ->
            if (ModelRules.useNeedsConfirmation(snapshot, row)) confirmation = Confirmation.Switch(row) else run { useModel(graph, row) }
        },
        cancel = { row -> row.sha256?.let { sha -> run { graph.server.cancelDownload(sha) } } },
        unload = { run { graph.server.unload() } },
        delete = { row -> confirmation = Confirmation.Delete(row) },
        refresh = refresh,
    )
    Scaffold(
        containerColor = JetlinkTheme.colors.grouped,
        topBar = {
            TopAppBar(
                title = { Text(l10n(R.string.tab_models), fontWeight = FontWeight.Bold) },
                actions = {
                    IconButton(onClick = refresh) { Icon(Icons.Filled.Refresh, contentDescription = l10n(R.string.content_desc_refresh)) }
                    IconButton(onClick = { picker.launch(arrayOf("*/*")) }) {
                        Icon(Icons.Filled.Add, contentDescription = l10n(R.string.content_desc_add_model))
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = JetlinkTheme.colors.grouped,
                    scrolledContainerColor = JetlinkTheme.colors.grouped,
                ),
            )
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = refreshing,
            onRefresh = refresh,
            modifier = Modifier.padding(padding).consumeWindowInsets(padding).fillMaxSize(),
        ) {
            ModelsContent(snapshot, actions)
        }
    }

    when (val item = confirmation) {
        is Confirmation.Delete -> AlertDialog(
            onDismissRequest = { confirmation = null },
            title = { Text(l10n(R.string.model_delete_title, item.row.title)) },
            text = { Text(l10n(R.string.model_delete_text)) },
            confirmButton = {
                TextButton(onClick = {
                    confirmation = null
                    item.row.sha256?.let { sha -> run { graph.server.forget(sha, artifacts = true, model = true) } }
                }) { Text(l10n(R.string.action_delete), color = JetlinkTheme.colors.bad) }
            },
            dismissButton = { TextButton(onClick = { confirmation = null }) { Text(l10n(R.string.action_cancel)) } },
        )
        is Confirmation.Switch -> AlertDialog(
            onDismissRequest = { confirmation = null },
            title = { Text(l10n(R.string.model_use_title, item.row.title)) },
            text = { Text(l10n(R.string.model_use_text)) },
            confirmButton = {
                TextButton(onClick = {
                    confirmation = null
                    run { useModel(graph, item.row) }
                }) { Text(l10n(R.string.action_use_model)) }
            },
            dismissButton = { TextButton(onClick = { confirmation = null }) { Text(l10n(R.string.action_cancel)) } },
        )
        null -> {}
    }

    error?.let { message ->
        AlertDialog(
            onDismissRequest = { error = null },
            title = { Text(l10n(R.string.error_title)) },
            text = { Text(Format.sentence(message)) },
            confirmButton = { TextButton(onClick = { error = null }) { Text(l10n(R.string.ok)) } },
        )
    }
}

/** The list itself, without the server, for previews. */
@Composable
fun ModelsContent(snapshot: Snapshot, actions: ModelActions, modifier: Modifier = Modifier) {
    val colors = JetlinkTheme.colors
    if (snapshot.catalog == null && snapshot.models.isEmpty()) {
        Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        return
    }
    val sections = ModelRules.sections(snapshot.models)
    val catalogError = snapshot.catalog?.error?.takeIf { it.isNotBlank() }
    val imports = ModelRules.activeImports(snapshot.imports)
    LazyColumn(
        modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = CardSpacing, end = CardSpacing, top = 8.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        item("available") {
            FormSection(
                l10n(R.string.section_available),
                footer = if (catalogError != null) {
                    { FooterNote(l10n(R.string.catalog_refresh_failed), warning = true) }
                } else {
                    null
                },
            ) {
                if (sections.available.isEmpty()) {
                    CatalogPlaceholder(catalogError != null, actions.refresh)
                }
                Rows(sections.available, actions)
            }
        }
        if (imports.isNotEmpty()) {
            item("adding") {
                FormSection(l10n(R.string.section_adding)) {
                    imports.forEachIndexed { index, import ->
                        if (index > 0) RowDivider()
                        ImportRow(import)
                    }
                }
            }
        }
        if (sections.added.isNotEmpty()) {
            item("added") { FormSection(l10n(R.string.section_added)) { Rows(sections.added, actions) } }
        }
        if (sections.uploaded.isNotEmpty()) {
            item("uploaded") { FormSection(l10n(R.string.section_uploaded)) { Rows(sections.uploaded, actions) } }
        }
        ModelRules.diskLine(snapshot)?.let { line ->
            item("disk") {
                Text(
                    line,
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.secondaryText,
                    modifier = Modifier.widthIn(max = ReadableWidth).fillMaxWidth().padding(horizontal = 16.dp),
                )
            }
        }
    }
}

@Composable
private fun FooterNote(text: String, warning: Boolean = false) {
    val colors = JetlinkTheme.colors
    Row(verticalAlignment = Alignment.CenterVertically) {
        if (warning) {
            Icon(Icons.Filled.Warning, contentDescription = null, tint = colors.warning, modifier = Modifier.size(14.dp))
            Spacer(Modifier.width(6.dp))
        }
        Text(text, style = MaterialTheme.typography.bodySmall, color = colors.secondaryText)
    }
}

/** The Available section while the list has nothing in it: loading, or why not. */
@Composable
private fun CatalogPlaceholder(failed: Boolean, retry: () -> Unit) {
    val colors = JetlinkTheme.colors
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        if (failed) {
            Icon(Icons.Filled.Warning, contentDescription = null, tint = colors.secondaryText, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Text(l10n(R.string.catalog_load_failed), color = colors.secondaryText, modifier = Modifier.weight(1f))
            OutlinedButton(onClick = retry) { Text(l10n(R.string.action_try_again)) }
        } else {
            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
            Spacer(Modifier.width(10.dp))
            Text(l10n(R.string.loading), color = colors.secondaryText)
        }
    }
}

@Composable
private fun Rows(rows: List<ModelRow>, actions: ModelActions) {
    rows.forEachIndexed { index, row ->
        if (index > 0) RowDivider()
        ModelRowView(row, actions)
    }
}

/** One model: its name, one line of facts or progress, and the button. */
@Composable
fun ModelRowView(row: ModelRow, actions: ModelActions) {
    val colors = JetlinkTheme.colors
    var menu by remember { mutableStateOf(false) }
    val action = ModelRules.action(row)
    val canDelete = row.hasFiles
    // The row's menu holds what its button does not: stopping and deleting.
    val hasMenu = canDelete || action == RowAction.InUse
    Row(
        Modifier.fillMaxWidth().padding(start = 16.dp, end = if (hasMenu && action != RowAction.InUse) 4.dp else 12.dp, top = 10.dp, bottom = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    row.title,
                    style = MaterialTheme.typography.bodyLarge,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                if (row.isDefault) Tag(l10n(R.string.tag_default), MaterialTheme.colorScheme.primary)
                if (row.isRequestedByComma) Tag("Comma", colors.info)
            }
            Text(
                ModelRules.subtitle(row),
                style = MaterialTheme.typography.bodyMedium,
                color = colors.tone(ModelRules.subtitleTone(row)),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            ModelRules.failure(row)?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = colors.secondaryText, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
        Spacer(Modifier.width(8.dp))
        Box {
            when (action) {
                RowAction.InUse -> IconButton(onClick = { menu = true }) {
                    Icon(Icons.Filled.CheckCircle, contentDescription = l10n(R.string.content_desc_in_use), tint = colors.good, modifier = Modifier.size(28.dp))
                }
                RowAction.Stop -> IconButton(onClick = { actions.cancel(row) }) {
                    ProgressRing(row.status.frac, stoppable = true)
                }
                RowAction.Preparing -> ProgressRing(row.status.frac, stoppable = false)
                RowAction.Get, RowAction.Use, RowAction.Retry -> FilledTonalButton(
                    onClick = { actions.use(row) },
                    enabled = row.canUse,
                    contentPadding = PaddingValues(horizontal = 16.dp),
                    modifier = Modifier.height(32.dp),
                ) {
                    Text(
                        when (action) {
                            RowAction.Get -> l10n(R.string.action_get)
                            RowAction.Retry -> l10n(R.string.action_try_again)
                            else -> l10n(R.string.action_use)
                        },
                        fontWeight = FontWeight.Bold,
                    )
                }
                RowAction.None -> {}
            }
            if (action == RowAction.InUse) {
                RowMenu(menu, { menu = false }, row, canDelete, actions)
            }
        }
        if (hasMenu && action != RowAction.InUse) {
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Filled.MoreVert, contentDescription = l10n(R.string.content_desc_more)) }
                RowMenu(menu, { menu = false }, row, canDelete, actions)
            }
        }
    }
}

@Composable
private fun RowMenu(expanded: Boolean, dismiss: () -> Unit, row: ModelRow, canDelete: Boolean, actions: ModelActions) {
    DropdownMenu(expanded = expanded, onDismissRequest = dismiss) {
        if (row.status.kind == "downloading") {
            DropdownMenuItem(text = { Text(l10n(R.string.menu_stop_download)) }, onClick = { dismiss(); actions.cancel(row) })
        }
        if (row.status.kind == "loaded") {
            DropdownMenuItem(text = { Text(l10n(R.string.menu_stop_using)) }, onClick = { dismiss(); actions.unload() })
        }
        if (canDelete) {
            DropdownMenuItem(
                text = { Text(l10n(R.string.action_delete), color = JetlinkTheme.colors.bad) },
                onClick = { dismiss(); actions.delete(row) },
            )
        }
    }
}

/** A model file being added: checked, then copied into the cache. */
@Composable
private fun ImportRow(import: ImportState) {
    val colors = JetlinkTheme.colors
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(import.path.substringAfterLast('/'), style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(
            ModelRules.importLine(import),
            style = MaterialTheme.typography.bodyMedium,
            color = if (import.state == "failed") colors.bad else colors.secondaryText,
        )
        if (import.state == "hashing" || import.state == "copying") {
            LinearProgressIndicator(progress = { import.frac.coerceIn(0.0, 1.0).toFloat() }, modifier = Modifier.fillMaxWidth())
        } else if (import.state == "failed" && import.detail.isNotBlank()) {
            Text(Format.sentence(import.detail), style = MaterialTheme.typography.bodySmall, color = colors.secondaryText, maxLines = 2)
        }
    }
}

@Preview(showBackground = true, heightDp = 640)
@Composable
private fun ModelsPreview() {
    JetlinkTheme {
        Box(Modifier.fillMaxSize().background(JetlinkTheme.colors.grouped)) {
            ModelsContent(PreviewData.serving, ModelActions())
        }
    }
}

@Preview(showBackground = true, heightDp = 640, uiMode = android.content.res.Configuration.UI_MODE_NIGHT_YES)
@Composable
private fun ModelsDarkPreview() {
    JetlinkTheme(dark = true) {
        Box(Modifier.fillMaxSize().background(JetlinkTheme.colors.grouped)) {
            ModelsContent(PreviewData.preparing, ModelActions())
        }
    }
}
