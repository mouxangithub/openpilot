package io.zoompilot.jetlink.ui.status

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.BatteryUnknown
import androidx.compose.material.icons.automirrored.filled.ShowChart
import androidx.compose.material.icons.filled.ArrowCircleDown
import androidx.compose.material.icons.filled.Battery2Bar
import androidx.compose.material.icons.filled.Battery4Bar
import androidx.compose.material.icons.filled.Battery6Bar
import androidx.compose.material.icons.filled.BatteryAlert
import androidx.compose.material.icons.filled.BatteryChargingFull
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Cable
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.HourglassTop
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.LinkOff
import androidx.compose.material.icons.filled.Memory
import androidx.compose.material.icons.filled.Report
import androidx.compose.material.icons.filled.SlowMotionVideo
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.StopCircle
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material.icons.filled.Usb
import androidx.compose.material.icons.filled.Warning
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.device.DeviceHealth
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.server.Stats
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.Thermal
import io.zoompilot.jetlink.ui.components.CardSpacing
import io.zoompilot.jetlink.ui.components.HistoryChart
import io.zoompilot.jetlink.ui.components.LatencyBreakdown
import io.zoompilot.jetlink.ui.components.MetricRow
import io.zoompilot.jetlink.ui.components.MetricTile
import io.zoompilot.jetlink.ui.components.ReadableWidth
import io.zoompilot.jetlink.ui.components.SectionHeader
import io.zoompilot.jetlink.ui.components.SummaryCard
import io.zoompilot.jetlink.ui.components.tile
import io.zoompilot.jetlink.ui.icon
import io.zoompilot.jetlink.usb.UsbState

/** How the cards are set out, from the space there is. */
enum class CardLayout {
    /** One column, as a phone held upright shows them. */
    Column,

    /** The ring and beside it the numbers, as a phone on its side shows them. */
    Sideways,

    /** Two columns, for the width of a tablet. */
    Columns,
}

/**
 * The Status tab's cards, most important first: the headroom, where the time
 * goes, the last two minutes, then the link and the phone.
 */
@Composable
fun StatusContent(state: StatusState, modifier: Modifier = Modifier, actions: StatusActions = StatusActions()) {
    BoxWithConstraints(modifier.fillMaxSize()) {
        val layout = when {
            maxHeight < 480.dp && maxWidth > maxHeight -> CardLayout.Sideways
            maxWidth >= 840.dp -> CardLayout.Columns
            else -> CardLayout.Column
        }
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = CardSpacing)
                .padding(bottom = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Column(
                Modifier
                    .then(if (layout == CardLayout.Column) Modifier.widthIn(max = ReadableWidth) else Modifier)
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                verticalArrangement = Arrangement.spacedBy(CardSpacing),
            ) {
                Banners(state)
                Cards(state, layout, actions)
            }
        }
    }
}

/** The USB trouble the hero does not already show. */
@Composable
private fun Banners(state: StatusState) {
    val usb = state.usb
    if (usb == UsbState.NeedsPermission && state.hero != StatusState.Hero.Waiting && !state.connected) {
        AllowUsbBanner()
    }
    if (usb is UsbState.Failed && !state.connected) {
        WarningBanner(Format.sentence(usb.reason))
    }
}

@Composable
private fun AllowUsbBanner() {
    WarningBanner(l10n(R.string.banner_allow_usb))
}

@Composable
private fun Cards(state: StatusState, layout: CardLayout, actions: StatusActions) {
    val spacing = Arrangement.spacedBy(CardSpacing)
    val serving = if (state.isServingFrames) state.recent else null
    when (layout) {
        CardLayout.Column -> {
            HeroCard(state, actions = actions)
            if (serving != null) {
                LatencyCard(serving)
                if (state.history.size > 1) HistoryCard(state)
                SectionHeader(l10n(R.string.section_link), detail = state.medium?.title)
                LinkTiles(serving)
            }
            SectionHeader(l10n(R.string.section_phone))
            DeviceTiles(state)
        }
        CardLayout.Sideways -> Row(horizontalArrangement = spacing) {
            HeroCard(state, Modifier.width(330.dp), compact = true, actions = actions)
            Column(Modifier.weight(1f), verticalArrangement = spacing) {
                if (serving != null) {
                    LatencyCard(serving, compact = true)
                    LinkTiles(serving)
                } else {
                    DeviceTiles(state)
                }
            }
        }
        // The headroom and where the time goes on the left; the history, the
        // link and the phone on the right.
        CardLayout.Columns -> Row(horizontalArrangement = spacing) {
            Column(Modifier.weight(1f), verticalArrangement = spacing) {
                HeroCard(state, actions = actions)
                if (serving != null) LatencyCard(serving)
            }
            Column(Modifier.weight(1f), verticalArrangement = spacing) {
                if (serving != null) {
                    if (state.history.size > 1) HistoryCard(state)
                    SectionHeader(l10n(R.string.section_link), detail = state.medium?.title)
                    LinkTiles(serving)
                }
                SectionHeader(l10n(R.string.section_phone))
                DeviceTiles(state)
            }
        }
    }
}

@Composable
private fun LatencyCard(recent: Stats, compact: Boolean = false) {
    SummaryCard(l10n(R.string.section_latency), Icons.Filled.Timer, JetlinkTheme.colors.info, trailing = l10n(R.string.last_10s)) {
        LatencyBreakdown(recent, compact = compact)
    }
}

@Composable
private fun HistoryCard(state: StatusState) {
    SummaryCard(l10n(R.string.section_history), Icons.AutoMirrored.Filled.ShowChart, JetlinkTheme.colors.purple, trailing = l10n(R.string.last_2min)) {
        HistoryChart(state.history)
    }
}

@Composable
private fun LinkTiles(recent: Stats) {
    val colors = JetlinkTheme.colors
    MetricRow {
        MetricTile(
            l10n(R.string.tile_frame_rate), Icons.Filled.Speed, colors.teal, Format.decimal(recent.fps), tile(),
            unit = "fps",
            note = if (recent.fps < 18) l10n(R.string.note_below_20) else null,
            noteColor = colors.warning,
        )
        MetricTile(
            l10n(R.string.tile_slow_frames), Icons.Filled.SlowMotionVideo, colors.pink, Format.integer(recent.slow), tile(),
            note = if (recent.slow > 0) l10n(R.string.note_over_60ms) else null,
            noteColor = colors.bad,
        )
    }
}

@Composable
private fun DeviceTiles(state: StatusState) {
    val colors = JetlinkTheme.colors
    val health = state.health
    val thermal = DeviceText.thermal(health)
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        MetricRow {
            MetricTile(
                l10n(R.string.tile_temperature), thermal.icon, colors.orange, StatusL10n.thermalTitle(thermal), tile(),
                note = StatusL10n.temperatureNote(health),
                noteColor = colors.tone(thermal.tone),
            )
            MetricTile(
                l10n(R.string.tile_battery), batteryIcon(health), colors.good, DeviceText.batteryValue(health), tile(),
                unit = if (health.batteryLevel == null) null else "%",
                note = StatusL10n.powerText(health),
                noteColor = colors.tone(DeviceText.batteryTone(health)),
            )
        }
        MetricRow {
            MetricTile(
                l10n(R.string.tile_memory), Icons.Filled.Memory, colors.indigo, DeviceText.memoryValue(health), tile(),
                unit = if (health.availableMemory > 0) "GB" else null,
                note = StatusL10n.memoryNote(health),
                noteColor = colors.tone(DeviceText.memoryTone(health)),
            )
            MetricTile(
                l10n(R.string.tile_link), if (state.medium == null) Icons.Filled.LinkOff else Icons.Filled.Cable, colors.teal,
                state.medium?.title ?: l10n(R.string.link_none), tile(),
                note = StatusL10n.linkNote(state),
                noteColor = if (state.medium?.slow == true) colors.warning else null,
            )
        }
    }
}

private fun batteryIcon(health: DeviceHealth): ImageVector {
    val level = health.batteryLevel ?: return Icons.AutoMirrored.Filled.BatteryUnknown
    return when {
        health.charging -> Icons.Filled.BatteryChargingFull
        level > 66 -> Icons.Filled.Battery6Bar
        level > 33 -> Icons.Filled.Battery4Bar
        level > 15 -> Icons.Filled.Battery2Bar
        else -> Icons.Filled.BatteryAlert
    }
}

/** The summary's icon, beside its words above the tabs. */
fun summaryIcon(summary: StatusState.Summary): ImageVector = when (summary) {
    StatusState.Summary.Failed -> Icons.Filled.Report
    StatusState.Summary.Starting -> Icons.Filled.HourglassTop
    StatusState.Summary.Stopped -> Icons.Filled.StopCircle
    StatusState.Summary.Preparing -> Icons.Filled.Build
    StatusState.Summary.Loading -> Icons.Filled.ArrowCircleDown
    StatusState.Summary.ModelFailed -> Icons.Filled.Warning
    StatusState.Summary.AllowUsb -> Icons.Filled.Usb
    StatusState.Summary.Connected, StatusState.Summary.ConnectedSlow -> Icons.Filled.DirectionsCar
    StatusState.Summary.NoModel -> Icons.Filled.Inventory2
    StatusState.Summary.Waiting -> Icons.Filled.Cable
    StatusState.Summary.Disconnected -> Icons.Filled.LinkOff
}
