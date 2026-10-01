package io.zoompilot.jetlink.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.zoompilot.jetlink.AppGraph
import io.zoompilot.jetlink.AppLocale
import io.zoompilot.jetlink.BuildConfig
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.server.RunState
import io.zoompilot.jetlink.server.ServerService
import io.zoompilot.jetlink.server.Snapshot
import io.zoompilot.jetlink.settings.Chip
import io.zoompilot.jetlink.settings.Processor
import io.zoompilot.jetlink.settings.SettingsValues
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.PreviewData
import io.zoompilot.jetlink.ui.components.ActionRow
import io.zoompilot.jetlink.ui.components.CardSpacing
import io.zoompilot.jetlink.ui.components.FormFooter
import io.zoompilot.jetlink.ui.components.FormSection
import io.zoompilot.jetlink.ui.components.RowDivider
import io.zoompilot.jetlink.ui.components.SwitchRow
import io.zoompilot.jetlink.ui.components.ValueRow
import io.zoompilot.jetlink.ui.components.rememberWifiAddress
import io.zoompilot.jetlink.usb.UsbState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** What the Settings rows show beyond the settings themselves. */
data class SettingsInfo(
    val snapshot: Snapshot,
    val runState: RunState,
    val usb: UsbState,
    val wifi: String?,
    /** onnxruntime's version, from the server's info. */
    val runtime: String?,
    val chip: String,
    val version: String,
    /** The emulator also offers the CPU. */
    val offerCpu: Boolean,
)

/** What the Settings rows do. */
class SettingsActions(
    val update: ((SettingsValues) -> SettingsValues) -> Unit = {},
    val openConnect: () -> Unit = {},
    val openLogs: () -> Unit = {},
    val stopServer: () -> Unit = {},
    val startServer: () -> Unit = {},
    val restartServer: () -> Unit = {},
)

/**
 * Connection, performance, display, storage, help and versions. A change the
 * server runs with restarts it (ServerService does that).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(graph: AppGraph, openConnect: () -> Unit, openLogs: () -> Unit) {
    val context = LocalContext.current
    val values by graph.settings.values.collectAsStateWithLifecycle()
    val snapshot by graph.server.snapshot.collectAsStateWithLifecycle()
    val runState by graph.server.runState.collectAsStateWithLifecycle()
    val usb by graph.usb.usb.collectAsStateWithLifecycle()
    val wifi = rememberWifiAddress()
    val runtime by produceState<String?>(null, runState) {
        value = withContext(Dispatchers.IO) { graph.server.runtimeVersion() }
    }
    val info = SettingsInfo(
        snapshot = snapshot,
        runState = runState,
        usb = usb,
        wifi = wifi,
        runtime = snapshot.server?.runtimeVersion ?: runtime,
        chip = Chip.name,
        version = BuildConfig.VERSION_NAME,
        offerCpu = Chip.isEmulator || values.processor == Processor.Cpu,
    )
    val actions = SettingsActions(
        update = graph.settings::update,
        openConnect = openConnect,
        openLogs = openLogs,
        stopServer = { ServerService.start(context, ServerService.ACTION_STOP) },
        startServer = { ServerService.start(context) },
        restartServer = { graph.restartServer(context) },
    )
    Scaffold(
        containerColor = JetlinkTheme.colors.grouped,
        topBar = {
            TopAppBar(
                title = { Text(l10n(R.string.tab_settings), fontWeight = FontWeight.Bold) },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = JetlinkTheme.colors.grouped,
                    scrolledContainerColor = JetlinkTheme.colors.grouped,
                ),
            )
        },
    ) { padding ->
        SettingsContent(values, info, actions, Modifier.padding(padding).consumeWindowInsets(padding))
    }
}

@Composable
fun SettingsContent(values: SettingsValues, info: SettingsInfo, actions: SettingsActions, modifier: Modifier = Modifier) {
    Column(
        modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = CardSpacing)
            .padding(top = 8.dp, bottom = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        Connection(values, info, actions)
        Performance(values, info, actions)
        DisplayAndLanguage(values, actions)
        info.snapshot.disk?.let { disk ->
            FormSection(l10n(R.string.settings_storage)) {
                ValueRow(l10n(R.string.storage_downloaded), Format.bytes(disk.modelsBytes))
                RowDivider()
                ValueRow(l10n(R.string.storage_prepared), Format.bytes(disk.enginesBytes))
                disk.freeBytes?.let {
                    RowDivider()
                    ValueRow(l10n(R.string.storage_available), Format.bytes(it))
                }
            }
        }
        FormSection(l10n(R.string.settings_help)) {
            ActionRow(l10n(R.string.help_connect), actions.openConnect)
            RowDivider()
            ActionRow(l10n(R.string.help_logs), actions.openLogs)
        }
        About(info, actions)
    }
}

/** Display and the app language. The choice applies at once, everywhere. */
@Composable
private fun DisplayAndLanguage(values: SettingsValues, actions: SettingsActions) {
    var choosing by remember { mutableStateOf(false) }
    FormSection(l10n(R.string.settings_display), footer = { FormFooter(l10n(R.string.settings_display_footer)) }) {
        SwitchRow(l10n(R.string.settings_keep_screen_on), values.keepScreenOn, { on -> actions.update { it.copy(keepScreenOn = on) } })
        RowDivider()
        Box {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable(role = Role.DropdownList) { choosing = true }
                    .heightIn(min = 48.dp)
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(l10n(R.string.settings_language), style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                Spacer(Modifier.width(12.dp))
                Text(values.language.displayName, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.primary)
            }
            DropdownMenu(expanded = choosing, onDismissRequest = { choosing = false }) {
                AppLocale.entries.forEach { locale ->
                    DropdownMenuItem(
                        text = { Text(locale.displayName, fontWeight = if (locale == values.language) FontWeight.SemiBold else null) },
                        onClick = {
                            choosing = false
                            if (locale != values.language) actions.update { it.copy(language = locale) }
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun Connection(values: SettingsValues, info: SettingsInfo, actions: SettingsActions) {
    val colors = JetlinkTheme.colors
    val focus = LocalFocusManager.current
    var portText by remember(values.port) { mutableStateOf(values.port.toString()) }
    val typed = portText.toIntOrNull()?.takeIf { it in 1..65535 }
    val apply = {
        if (typed != null && typed != values.port) {
            actions.update { it.copy(port = typed) }
        } else {
            portText = values.port.toString()
        }
        focus.clearFocus()
    }
    val link = info.snapshot.medium?.title
        ?: if (info.usb is UsbState.Attached) l10n(R.string.link_connecting) else l10n(R.string.link_not_connected)
    FormSection(l10n(R.string.settings_connection), footer = { FormFooter(l10n(R.string.settings_connection_footer)) }) {
        ValueRow(l10n(R.string.settings_link), link)
        RowDivider()
        Row(
            Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(l10n(R.string.settings_port), style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
            BasicTextField(
                value = portText,
                onValueChange = { text -> portText = text.filter(Char::isDigit).take(5) },
                singleLine = true,
                textStyle = MaterialTheme.typography.bodyLarge.copy(color = colors.secondaryText, textAlign = TextAlign.End),
                cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { apply() }),
                modifier = Modifier.width(96.dp),
            )
        }
        if (typed != null && typed != values.port) {
            RowDivider()
            ActionRow(l10n(R.string.settings_use_port, typed), { apply() }, color = MaterialTheme.colorScheme.primary, chevron = false)
        }
        info.wifi?.let { address ->
            RowDivider()
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(l10n(R.string.settings_wifi), style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                SelectionContainer {
                    Text("$address:${info.snapshot.port ?: values.port}", style = MaterialTheme.typography.bodyLarge, color = colors.secondaryText)
                }
            }
        }
    }
}

@Composable
private fun Performance(values: SettingsValues, info: SettingsInfo, actions: SettingsActions) {
    val colors = JetlinkTheme.colors
    var choosing by remember { mutableStateOf(false) }
    val choices = Processor.entries.filter { it != Processor.Cpu || info.offerCpu }
    FormSection(l10n(R.string.settings_performance), footer = { FormFooter(l10n(R.string.settings_performance_footer)) }) {
        Box {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable(role = Role.DropdownList) { choosing = true }
                    .heightIn(min = 48.dp)
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(l10n(R.string.settings_processor), style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                Spacer(Modifier.width(12.dp))
                Text(values.processor.title, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.primary)
            }
            DropdownMenu(expanded = choosing, onDismissRequest = { choosing = false }, modifier = Modifier.background(colors.card)) {
                choices.forEach { processor ->
                    DropdownMenuItem(
                        text = { Text(processor.title, fontWeight = if (processor == values.processor) FontWeight.SemiBold else null) },
                        onClick = {
                            choosing = false
                            if (processor != values.processor) actions.update { it.copy(processor = processor) }
                        },
                    )
                }
            }
        }
        RowDivider()
        SwitchRow(
            l10n(R.string.settings_keep_npu), values.keepNpuAwake, { on -> actions.update { it.copy(keepNpuAwake = on) } },
            supporting = l10n(R.string.settings_keep_npu_support),
        )
        RowDivider()
        SwitchRow(
            l10n(R.string.settings_keep_cpu), values.keepCpuAwake, { on -> actions.update { it.copy(keepCpuAwake = on) } },
            supporting = l10n(R.string.settings_keep_cpu_support),
        )
    }
}

@Composable
private fun About(info: SettingsInfo, actions: SettingsActions) {
    val colors = JetlinkTheme.colors
    val server = when (info.runState) {
        RunState.Stopped -> l10n(R.string.server_stopped)
        RunState.Starting -> l10n(R.string.server_starting)
        RunState.Serving -> l10n(R.string.server_running)
        is RunState.Failed -> l10n(R.string.server_failed)
    }
    FormSection(l10n(R.string.settings_about)) {
        ValueRow(l10n(R.string.about_version), info.version)
        RowDivider()
        ValueRow(l10n(R.string.about_runtime), info.runtime?.let { "onnxruntime $it" } ?: "onnxruntime")
        RowDivider()
        ValueRow(l10n(R.string.about_chip), info.chip)
        RowDivider()
        ValueRow(l10n(R.string.about_server), server, valueColor = if (info.runState is RunState.Failed) colors.bad else null)
        RowDivider()
        if (info.runState == RunState.Stopped) {
            ActionRow(l10n(R.string.action_start_server), actions.startServer, color = MaterialTheme.colorScheme.primary, chevron = false)
        } else {
            // a failed server's service still runs: it starts again, it is not started
            ActionRow(l10n(R.string.action_restart_server), actions.restartServer, color = MaterialTheme.colorScheme.primary, chevron = false)
            RowDivider()
            ActionRow(l10n(R.string.action_stop_server), actions.stopServer, color = colors.bad, chevron = false)
        }
    }
}

@Preview(showBackground = true, heightDp = 1300)
@Composable
private fun SettingsPreview() {
    JetlinkTheme {
        Column(Modifier.background(JetlinkTheme.colors.grouped)) {
            SettingsContent(
                SettingsValues(),
                SettingsInfo(
                    snapshot = PreviewData.serving,
                    runState = RunState.Serving,
                    usb = UsbState.Attached,
                    wifi = "192.168.1.23",
                    runtime = "1.29.0",
                    chip = "Snapdragon 8 Gen 3",
                    version = "0.5.0",
                    offerCpu = false,
                ),
                SettingsActions(),
            )
        }
    }
}
