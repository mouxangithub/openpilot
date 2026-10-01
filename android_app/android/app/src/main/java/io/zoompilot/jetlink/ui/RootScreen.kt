package io.zoompilot.jetlink.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.zoompilot.jetlink.AppGraph
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.ui.benchmark.BenchmarkScreen
import io.zoompilot.jetlink.ui.benchmark.BenchmarkText
import io.zoompilot.jetlink.ui.logs.LogsScreen
import io.zoompilot.jetlink.ui.models.ModelsScreen
import io.zoompilot.jetlink.ui.settings.ConnectHelpScreen
import io.zoompilot.jetlink.ui.settings.SettingsScreen
import io.zoompilot.jetlink.ui.status.StatusScreen
import io.zoompilot.jetlink.ui.status.StatusState
import io.zoompilot.jetlink.ui.status.rememberStatusState
import io.zoompilot.jetlink.ui.status.summaryIcon
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

enum class Tab(val titleRes: Int, val icon: ImageVector) {
    Status(R.string.tab_status, Icons.Filled.Speed),
    Models(R.string.tab_models, Icons.Filled.Inventory2),
    Benchmark(R.string.tab_benchmark, Icons.Filled.Timer),
    Settings(R.string.tab_settings, Icons.Filled.Settings),
}

/** A screen pushed over the tabs. */
enum class Pushed { Logs, Connect }

/** `-e tab models` and the like: the tab, and the screen pushed over it for logs and connect. */
fun initialTab(name: String?, launchBenchmark: Int?): Tab = when (name) {
    "models" -> Tab.Models
    "benchmark" -> Tab.Benchmark
    "settings", "logs", "connect" -> Tab.Settings
    "status" -> Tab.Status
    else -> if (launchBenchmark != null) Tab.Benchmark else Tab.Status
}

fun initialPushed(name: String?): Pushed? = when (name) {
    "logs" -> Pushed.Logs
    "connect" -> Pushed.Connect
    else -> null
}

/**
 * Four tabs: Status, Models, Benchmark and Settings. Away from Status, the
 * state rides along in a pill above the tabs, and a tap on it goes back. On
 * its side a phone shows Status as a dashboard, without the tabs.
 */
@Composable
fun RootScreen(graph: AppGraph, initialTab: String?, launchBenchmark: Int?) {
    var tab by rememberSaveable { mutableStateOf(initialTab(initialTab, launchBenchmark)) }
    var pushed by rememberSaveable { mutableStateOf(initialPushed(initialTab)) }
    val status = rememberStatusState(graph)
    val configuration = LocalConfiguration.current
    val sideways = configuration.screenHeightDp < 480 && configuration.screenWidthDp > configuration.screenHeightDp
    val showTabs = !(sideways && tab == Tab.Status && pushed == null)

    BackHandler(enabled = pushed != null || tab != Tab.Status) {
        if (pushed != null) pushed = null else tab = Tab.Status
    }
    ScriptedBenchmark(graph, launchBenchmark)
    ShutdownAlert(status.snapshot.shutdownRequests)

    Scaffold(
        containerColor = JetlinkTheme.colors.grouped,
        // each screen's own Scaffold keeps clear of the system bars
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            if (showTabs) {
                Column {
                    if (tab != Tab.Status) {
                        StatusAccessory(status) {
                            pushed = null
                            tab = Tab.Status
                        }
                    }
                    NavigationBar {
                        Tab.entries.forEach { item ->
                            NavigationBarItem(
                                selected = tab == item,
                                onClick = {
                                    pushed = null
                                    tab = item
                                },
                                icon = { Icon(item.icon, contentDescription = null) },
                                label = { Text(l10n(item.titleRes)) },
                            )
                        }
                    }
                }
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding).consumeWindowInsets(padding).fillMaxSize()) {
            val back = { pushed = null }
            when (pushed) {
                Pushed.Logs -> LogsScreen(graph, back)
                Pushed.Connect -> ConnectHelpScreen(back)
                null -> when (tab) {
                    Tab.Status -> StatusScreen(graph, status, openModels = { tab = Tab.Models }, openLogs = { pushed = Pushed.Logs })
                    Tab.Models -> ModelsScreen(graph)
                    Tab.Benchmark -> BenchmarkScreen(graph)
                    Tab.Settings -> SettingsScreen(graph, openConnect = { pushed = Pushed.Connect }, openLogs = { pushed = Pushed.Logs })
                }
            }
        }
    }
}

/** The state in one line, the summary's icon and words, then the headroom while serving, or the model. */
@Composable
private fun StatusAccessory(state: StatusState, onClick: () -> Unit) {
    val colors = JetlinkTheme.colors
    val summary = state.summary
    Box(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
        Surface(onClick = onClick, shape = CircleShape, color = colors.card, shadowElevation = 2.dp, modifier = Modifier.fillMaxWidth()) {
            Row(Modifier.padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(summaryIcon(summary), contentDescription = null, tint = colors.tone(summary.tone), modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(10.dp))
                Text(l10n(summary.titleRes), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, maxLines = 1)
                Spacer(Modifier.width(8.dp).weight(1f))
                Text(
                    state.accessoryDetail,
                    style = MaterialTheme.typography.bodyMedium,
                    color = colors.secondaryText,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

/** `--ei benchmark 60`: one run once a model is loaded, for benches and screenshots. */
@Composable
private fun ScriptedBenchmark(graph: AppGraph, seconds: Int?) {
    var done by rememberSaveable { mutableStateOf(false) }
    if (seconds == null || done) return
    LaunchedEffect(seconds) {
        combine(graph.server.snapshot, graph.server.runState) { snapshot, run -> BenchmarkText.blocker(run, snapshot) }
            .first { it == null }
        // on the app's scope, so leaving this composition does not cancel the command
        graph.scope.launch { graph.server.benchmark(seconds) }
        done = true
    }
}

/** The comma asked the phone to power off, which an app cannot do. */
@Composable
private fun ShutdownAlert(requests: Int) {
    var seen by rememberSaveable { mutableIntStateOf(requests) }
    if (requests > seen) {
        AlertDialog(
            onDismissRequest = { seen = requests },
            title = { Text(l10n(R.string.shutdown_title)) },
            // the reason the comma gave is in Logs
            text = { Text(l10n(R.string.shutdown_text)) },
            confirmButton = { TextButton(onClick = { seen = requests }) { Text(l10n(R.string.ok)) } },
        )
    }
}
