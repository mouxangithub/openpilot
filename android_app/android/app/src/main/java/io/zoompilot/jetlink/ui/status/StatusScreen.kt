package io.zoompilot.jetlink.ui.status

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Description
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.zoompilot.jetlink.AppGraph
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.server.RunState
import io.zoompilot.jetlink.server.ServerService
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.PreviewData
import io.zoompilot.jetlink.ui.Tone
import io.zoompilot.jetlink.ui.models.useModel
import io.zoompilot.jetlink.usb.UsbState
import kotlinx.coroutines.launch

/** The live state the Status tab and the bar above the tabs read. */
@Composable
fun rememberStatusState(graph: AppGraph): StatusState {
    val snapshot by graph.server.snapshot.collectAsStateWithLifecycle()
    val runState by graph.server.runState.collectAsStateWithLifecycle()
    val health by graph.device.health.collectAsStateWithLifecycle()
    val usb by graph.usb.usb.collectAsStateWithLifecycle()
    return StatusState(runState, snapshot, health, usb)
}

/**
 * The Status tab: the headroom and everything behind it, under a title whose
 * subtitle says where things stand.
 */
@Composable
fun StatusScreen(graph: AppGraph, state: StatusState, openModels: () -> Unit, openLogs: () -> Unit) {
    val context = LocalContext.current
    val actions = StatusActions(
        useDefault = { state.defaultModel?.let { row -> graph.scope.launch { useModel(graph, row) } } },
        openModels = openModels,
        retry = {
            val row = state.snapshot.row(state.engine.sha256)
            when {
                // a server that failed to start starts again
                state.runState is RunState.Failed -> graph.restartServer(context)
                // a failed model is asked for again
                row != null -> graph.scope.launch { useModel(graph, row) }
                else -> openModels()
            }
        },
        start = { ServerService.start(context) },
        refreshCatalog = { graph.scope.launch { graph.server.refreshCatalog() } },
        askUsb = graph.usb::connect,
    )
    LinkHaptics(state.snapshot.link.state)
    StatusScaffold(state, actions, openLogs)
}

/** A tap when the comma connects, and another when it goes. */
@Composable
private fun LinkHaptics(link: String) {
    val haptics = LocalHapticFeedback.current
    var previous by remember { mutableStateOf(link) }
    LaunchedEffect(link) {
        if (link == "connected" && previous != "connected") {
            haptics.performHapticFeedback(HapticFeedbackType.Confirm)
        } else if (previous == "connected" && link != "connected") {
            haptics.performHapticFeedback(HapticFeedbackType.Reject)
        }
        previous = link
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StatusScaffold(state: StatusState, actions: StatusActions, openLogs: () -> Unit) {
    val colors = JetlinkTheme.colors
    val summary = state.summary
    Scaffold(
        containerColor = colors.grouped,
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Jetlink", fontWeight = FontWeight.Bold, maxLines = 1)
                        Text(
                            StatusL10n.subtitle(state),
                            style = MaterialTheme.typography.bodyMedium,
                            color = if (summary.tone == Tone.Warning || summary.tone == Tone.Bad) colors.tone(summary.tone) else colors.secondaryText,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                },
                actions = {
                    IconButton(onClick = openLogs) { Icon(Icons.Filled.Description, contentDescription = l10n(R.string.content_desc_logs)) }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = colors.grouped, scrolledContainerColor = colors.grouped),
            )
        },
    ) { padding ->
        StatusContent(state, Modifier.padding(padding).consumeWindowInsets(padding), actions)
    }
}

@Composable
private fun PreviewFrame(state: StatusState, dark: Boolean = false) {
    JetlinkTheme(dark = dark) {
        Box(Modifier.fillMaxSize().background(JetlinkTheme.colors.grouped)) {
            StatusScaffold(state, StatusActions(), openLogs = {})
        }
    }
}

@Preview(showBackground = true, heightDp = 1500)
@Composable
private fun ServingPreview() {
    PreviewFrame(StatusState(RunState.Serving, PreviewData.serving, PreviewData.health, UsbState.Attached))
}

@Preview(showBackground = true, heightDp = 1500, uiMode = android.content.res.Configuration.UI_MODE_NIGHT_YES)
@Composable
private fun ServingDarkPreview() {
    PreviewFrame(StatusState(RunState.Serving, PreviewData.serving, PreviewData.health, UsbState.Attached), dark = true)
}

@Preview(showBackground = true, widthDp = 800, heightDp = 380)
@Composable
private fun SidewaysPreview() {
    PreviewFrame(StatusState(RunState.Serving, PreviewData.serving, PreviewData.health, UsbState.Attached))
}

@Preview(showBackground = true, heightDp = 800)
@Composable
private fun PreparingPreview() {
    PreviewFrame(StatusState(RunState.Serving, PreviewData.preparing, PreviewData.health))
}

@Preview(showBackground = true, heightDp = 800)
@Composable
private fun NoModelPreview() {
    PreviewFrame(StatusState(RunState.Serving, PreviewData.empty, PreviewData.health))
}

@Preview(showBackground = true, heightDp = 800)
@Composable
private fun AllowUsbPreview() {
    PreviewFrame(StatusState(RunState.Serving, PreviewData.waiting, PreviewData.health, UsbState.NeedsPermission))
}
