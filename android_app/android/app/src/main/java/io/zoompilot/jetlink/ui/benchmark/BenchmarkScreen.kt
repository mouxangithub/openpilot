package io.zoompilot.jetlink.ui.benchmark

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Cable
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Dangerous
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.Memory
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.filled.SlowMotionVideo
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.zoompilot.jetlink.AppGraph
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.server.BenchReport
import io.zoompilot.jetlink.server.BenchWindow
import io.zoompilot.jetlink.server.Benchmark
import io.zoompilot.jetlink.server.RunState
import io.zoompilot.jetlink.server.Snapshot
import io.zoompilot.jetlink.settings.Chip
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.PreviewData
import io.zoompilot.jetlink.ui.Thermal
import io.zoompilot.jetlink.ui.Tone
import io.zoompilot.jetlink.ui.Verdict
import io.zoompilot.jetlink.ui.components.CardSpacing
import io.zoompilot.jetlink.ui.components.FigureRow
import io.zoompilot.jetlink.ui.components.MetricRow
import io.zoompilot.jetlink.ui.components.MetricTile
import io.zoompilot.jetlink.ui.components.ReadableWidth
import io.zoompilot.jetlink.ui.components.SectionHeader
import io.zoompilot.jetlink.ui.components.SummaryCard
import io.zoompilot.jetlink.ui.components.copy
import io.zoompilot.jetlink.ui.components.rememberWifiAddress
import io.zoompilot.jetlink.ui.components.share
import io.zoompilot.jetlink.ui.components.tile
import io.zoompilot.jetlink.ui.icon
import io.zoompilot.jetlink.ui.status.StatusL10n
import kotlinx.coroutines.launch

/** The phone's chip, as the run card names it. */
data class ChipInfo(val line: String, val expectationRes: Int, val tone: Tone) {
    companion object {
        fun current(): ChipInfo {
            val (res, tone) = BenchmarkText.expectation(Chip.expectation)
            return ChipInfo(BenchmarkText.chipLine(Chip.name, Chip.hexagon), res, tone)
        }
    }
}

/** What the Benchmark tab's buttons do. */
class BenchmarkActions(
    val start: (Int) -> Unit = {},
    val cancel: () -> Unit = {},
    val openGuide: () -> Unit = {},
)

/**
 * Is this phone fast enough, and does it stay fast enough? The loaded model
 * at the comma's pace on the phone alone, then the commands that add the
 * cable from the comma and check the numbers from a Mac.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BenchmarkScreen(graph: AppGraph) {
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val snapshot by graph.server.snapshot.collectAsStateWithLifecycle()
    val runState by graph.server.runState.collectAsStateWithLifecycle()
    val settings by graph.settings.values.collectAsStateWithLifecycle()
    val wifi = rememberWifiAddress()
    var refusal by remember { mutableStateOf<String?>(null) }
    var starting by remember { mutableStateOf(false) }
    val chip = remember { ChipInfo.current() }
    val actions = BenchmarkActions(
        start = { seconds ->
            refusal = null
            starting = true
            graph.scope.launch {
                val reply = graph.server.benchmark(seconds)
                if (!reply.ok) {
                    refusal = reply.error?.let(Format::sentence)
                }
                starting = false
            }
        },
        cancel = { graph.scope.launch { graph.server.cancelBenchmark() } },
        openGuide = { runCatching { uriHandler.openUri(BenchmarkText.GUIDE) } },
    )
    val report = snapshot.benchmark?.report
    val reportText = snapshot.benchmark?.reportText
    Scaffold(
        containerColor = JetlinkTheme.colors.grouped,
        topBar = {
            TopAppBar(
                title = { Text(l10n(R.string.tab_benchmark), fontWeight = FontWeight.Bold) },
                actions = {
                    if (report != null && reportText != null) {
                        IconButton(onClick = { share(context, reportText, "Jetlink Benchmark") }) {
                            Icon(Icons.Filled.Share, contentDescription = l10n(R.string.content_desc_share))
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = JetlinkTheme.colors.grouped,
                    scrolledContainerColor = JetlinkTheme.colors.grouped,
                ),
            )
        },
    ) { padding ->
        BenchmarkContent(
            snapshot = snapshot,
            runState = runState,
            processor = settings.processor.title,
            chip = chip,
            wifi = wifi,
            refusal = refusal,
            starting = starting,
            actions = actions,
            modifier = Modifier.padding(padding).consumeWindowInsets(padding),
        )
    }
}

/** The run, its results and the commands, without the server, for previews. */
@Composable
fun BenchmarkContent(
    snapshot: Snapshot,
    runState: RunState,
    processor: String,
    chip: ChipInfo,
    wifi: String?,
    refusal: String?,
    starting: Boolean,
    actions: BenchmarkActions,
    modifier: Modifier = Modifier,
) {
    val sha = BenchmarkText.loadedSha(snapshot)
    val parity = BenchmarkText.parityCommand(sha, snapshot.row(sha)?.bytes, wifi, snapshot.port)
    val runCards: @Composable ColumnScope.() -> Unit = {
        RunCard(snapshot, runState, processor, chip, refusal, starting, actions)
        snapshot.benchmark?.report?.let { report ->
            VerdictCard(report)
            Totals(report)
            if (report.windows.size > 1) WindowsCard(report.windows)
        }
    }
    val commandCards: @Composable ColumnScope.() -> Unit = {
        SectionHeader(l10n(R.string.section_from_comma))
        CommandCard(
            l10n(R.string.bench_over_cable), Icons.Filled.Cable, BenchmarkText.COMMA_COMMAND,
            missing = l10n(R.string.bench_missing_model),
            note = l10n(R.string.bench_note_comma),
        )
        SectionHeader(l10n(R.string.section_accuracy))
        CommandCard(
            l10n(R.string.bench_from_mac), Icons.Filled.Verified, parity,
            missing = if (wifi == null) l10n(R.string.bench_missing_wifi) else l10n(R.string.bench_missing_model),
            note = l10n(R.string.bench_note_mac),
        )
        TextButton(onClick = actions.openGuide) { Text(l10n(R.string.action_learn_more)) }
    }
    val spacing = Arrangement.spacedBy(CardSpacing)
    BoxWithConstraints(modifier.fillMaxSize()) {
        val wide = maxWidth >= 840.dp
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = CardSpacing).padding(top = 8.dp, bottom = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            if (wide) {
                // A tablet has room for the run beside the commands.
                Row(horizontalArrangement = spacing) {
                    Column(Modifier.weight(1f), verticalArrangement = spacing, content = runCards)
                    Column(Modifier.weight(1f), verticalArrangement = spacing, content = commandCards)
                }
            } else {
                Column(Modifier.widthIn(max = ReadableWidth).fillMaxWidth(), verticalArrangement = spacing) {
                    runCards()
                    commandCards()
                }
            }
        }
    }
}

@Composable
private fun RunCard(
    snapshot: Snapshot,
    runState: RunState,
    processor: String,
    chip: ChipInfo,
    refusal: String?,
    starting: Boolean,
    actions: BenchmarkActions,
) {
    val colors = JetlinkTheme.colors
    val sha = BenchmarkText.loadedSha(snapshot)
    val event = snapshot.benchmark
    val running = BenchmarkText.running(snapshot)
    val blocker = BenchmarkText.blocker(runState, snapshot)
    SummaryCard(l10n(R.string.tab_benchmark), Icons.Filled.Timer, colors.info, trailing = processor) {
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                sha?.let { snapshot.modelName(it) ?: l10n(R.string.placeholder_model) } ?: l10n(R.string.summary_no_model),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )
            Text(
                buildAnnotatedString {
                    withStyle(SpanStyle(color = colors.secondaryText)) { append(chip.line + " · ") }
                    withStyle(SpanStyle(color = colors.tone(chip.tone))) { append(l10n(chip.expectationRes)) }
                },
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        if (event != null && running) {
            Progress(event, actions.cancel)
        } else {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                val enabled = blocker == null && !starting
                Button(onClick = { actions.start(60) }, enabled = enabled, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Filled.PlayArrow, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(l10n(R.string.bench_1min))
                }
                FilledTonalButton(onClick = { actions.start(600) }, enabled = enabled, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Filled.LocalFireDepartment, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(l10n(R.string.bench_10min))
                }
            }
        }
        val failure = refusal?.let { l10n(R.string.bench_refusal) + " " + it }
            ?: if (event?.state == "failed") l10n(R.string.bench_failed) else null
        if (failure != null) {
            Text(failure, style = MaterialTheme.typography.bodySmall, color = colors.bad)
        } else if (!running && blocker != null) {
            Text(l10n(blocker), style = MaterialTheme.typography.bodySmall, color = colors.warning)
        }
        Text(l10n(R.string.bench_hint), style = MaterialTheme.typography.bodySmall, color = colors.secondaryText)
    }
}

@Composable
private fun Progress(event: Benchmark, cancel: () -> Unit) {
    val colors = JetlinkTheme.colors
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        LinearProgressIndicator(
            progress = { (event.elapsed / maxOf(event.total, 1.0)).coerceIn(0.0, 1.0).toFloat() },
            modifier = Modifier.fillMaxWidth(),
            color = colors.info,
            trackColor = colors.info.copy(alpha = 0.2f),
        )
        Row {
            Text(
                l10n(R.string.bench_elapsed, Format.clock(event.elapsed), Format.clock(event.total)),
                style = MaterialTheme.typography.bodyMedium,
                color = colors.secondaryText,
                modifier = Modifier.weight(1f),
            )
            Text(l10n(R.string.bench_frames, Format.integer(event.frames)), style = MaterialTheme.typography.bodyMedium, color = colors.secondaryText)
        }
        FigureRow(listOf(Triple("P50", event.frame?.p50, Color.Unspecified), Triple("P99", event.frame?.p99, Color.Unspecified)))
        OutlinedButton(
            onClick = cancel,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = colors.bad),
        ) {
            Icon(Icons.Filled.Stop, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text(l10n(R.string.action_cancel))
        }
    }
}

private fun verdictIcon(verdict: Verdict): ImageVector = when (verdict) {
    Verdict.Good -> Icons.Filled.Verified
    Verdict.Tight -> Icons.Filled.Warning
    Verdict.Slow -> Icons.Filled.Dangerous
}

/** Fast enough, tight, or too slow, and the numbers that say so. */
@Composable
private fun VerdictCard(report: BenchReport) {
    val colors = JetlinkTheme.colors
    val verdict = Verdict.of(report.frame.p99, report.over50)
    val tone = colors.tone(verdict.tone)
    SummaryCard(l10n(R.string.bench_verdict), verdictIcon(verdict), tone, trailing = if (report.cancelled) l10n(R.string.verdict_stopped_early) else null) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(BenchmarkText.verdictTitle(verdict), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = tone)
            Text(BenchmarkText.verdictDetail(verdict), style = MaterialTheme.typography.bodyMedium, color = colors.secondaryText)
        }
        FigureRow(
            listOf(
                Triple("P99", report.frame.p99, tone),
                Triple(l10n(R.string.label_max), report.frame.max, Color.Unspecified),
                Triple(l10n(R.string.label_mean), report.frame.mean, Color.Unspecified),
            ),
        )
    }
}

@Composable
private fun Totals(report: BenchReport) {
    val colors = JetlinkTheme.colors
    val thermal = Thermal.of(report.thermalAtEnd)
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        MetricRow {
            MetricTile(
                l10n(R.string.tile_frames), Icons.Filled.Movie, colors.teal, Format.integer(report.frames), tile(),
                note = BenchmarkText.framesNote(report),
            )
            MetricTile(
                l10n(R.string.tile_over_budget), Icons.Filled.SlowMotionVideo, colors.pink, Format.integer(report.over50), tile(),
                note = BenchmarkText.overNote(report),
                noteColor = if (report.over50 > 0) colors.bad else null,
            )
        }
        MetricRow {
            MetricTile(
                l10n(R.string.tile_temperature), thermal.icon, colors.orange, StatusL10n.thermalTitle(thermal), tile(),
                note = BenchmarkText.thermalNote(report),
                noteColor = colors.tone(thermal.tone),
            )
            MetricTile(
                l10n(R.string.placeholder_model), Icons.Filled.Memory, colors.purple, Format.decimal(report.accelerator.mean), tile(),
                unit = "ms",
                note = l10n(R.string.bench_model_note),
            )
        }
    }
}

/** The run ten seconds at a time, with the phone's temperature as each closed. */
@Composable
private fun WindowsCard(windows: List<BenchWindow>) {
    val colors = JetlinkTheme.colors
    SummaryCard(l10n(R.string.section_over_time), Icons.Filled.BarChart, colors.indigo, trailing = l10n(R.string.bench_10s_each)) {
        Column {
            windows.forEachIndexed { index, window ->
                if (index > 0) HorizontalDivider()
                val thermal = Thermal.of(window.thermal)
                val verdict = Verdict.of(window.frame.p99)
                Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        Format.clock(window.startSecond.toDouble()),
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.secondaryText,
                        modifier = Modifier.width(48.dp),
                    )
                    Text(
                        "P99 ${Format.ms(window.frame.p99)}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (verdict == Verdict.Good) Color.Unspecified else colors.tone(verdict.tone),
                        modifier = Modifier.weight(1f),
                    )
                    Icon(thermal.icon, contentDescription = null, tint = colors.tone(thermal.tone), modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(StatusL10n.thermalTitle(thermal), style = MaterialTheme.typography.bodyMedium, color = colors.tone(thermal.tone))
                }
            }
        }
    }
}

/** A shell command with a Copy button, or why there is none yet. */
@Composable
private fun CommandCard(title: String, icon: ImageVector, command: String?, missing: String, note: String) {
    val context = LocalContext.current
    val colors = JetlinkTheme.colors
    var copied by remember(command) { mutableStateOf(false) }
    SummaryCard(title, icon, colors.gray) {
        if (command != null) {
            SelectionContainer {
                Text(command, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
            }
            FilledTonalButton(onClick = {
                copy(context, title, command)
                copied = true
            }) {
                Icon(if (copied) Icons.Filled.Check else Icons.Filled.ContentCopy, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text(if (copied) l10n(R.string.bench_copied) else l10n(R.string.action_copy))
            }
        } else {
            Text(missing, style = MaterialTheme.typography.bodyMedium, color = colors.secondaryText)
        }
        Text(note, style = MaterialTheme.typography.bodySmall, color = colors.secondaryText)
    }
}

@Preview(showBackground = true, heightDp = 1400)
@Composable
private fun BenchmarkPreview() {
    JetlinkTheme {
        Column(Modifier.background(JetlinkTheme.colors.grouped)) {
            BenchmarkContent(
                snapshot = PreviewData.serving.copy(link = PreviewData.waiting.link, medium = null),
                runState = RunState.Serving,
                processor = "NPU + GPU",
                chip = ChipInfo("Snapdragon 8 Gen 3 · NPU v75", R.string.expectation_should, Tone.Good),
                wifi = "192.168.1.23",
                refusal = null,
                starting = false,
                actions = BenchmarkActions(),
            )
        }
    }
}

@Preview(showBackground = true, heightDp = 700, uiMode = android.content.res.Configuration.UI_MODE_NIGHT_YES)
@Composable
private fun BenchmarkRunningPreview() {
    JetlinkTheme(dark = true) {
        Column(Modifier.background(JetlinkTheme.colors.grouped)) {
            BenchmarkContent(
                snapshot = PreviewData.waiting.copy(
                    benchmark = Benchmark(state = "running", elapsed = 12.0, total = 60.0, frames = 240, frame = PreviewData.report.frame),
                ),
                runState = RunState.Serving,
                processor = "NPU + GPU",
                chip = ChipInfo("Snapdragon 8 Gen 2 · NPU v73", R.string.expectation_possible, Tone.Warning),
                wifi = null,
                refusal = null,
                starting = false,
                actions = BenchmarkActions(),
            )
        }
    }
}
