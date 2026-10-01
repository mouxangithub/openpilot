package io.zoompilot.jetlink.ui.status

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Cable
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.StopCircle
import androidx.compose.material.icons.filled.Usb
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.ReportProblem
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.server.Engine
import io.zoompilot.jetlink.server.Stats
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.Room
import io.zoompilot.jetlink.ui.components.EmptyState
import io.zoompilot.jetlink.ui.components.FigureRow
import io.zoompilot.jetlink.ui.components.HeadroomRing
import io.zoompilot.jetlink.ui.components.SummaryCard
import io.zoompilot.jetlink.ui.components.cardBackground
import io.zoompilot.jetlink.usb.UsbState

/** What the Status tab's buttons do, handed down from the screen. */
class StatusActions(
    val useDefault: () -> Unit = {},
    val openModels: () -> Unit = {},
    val retry: () -> Unit = {},
    val start: () -> Unit = {},
    val refreshCatalog: () -> Unit = {},
    val askUsb: () -> Unit = {},
)

/**
 * The main card: the headroom while the comma is served, and otherwise
 * whatever stands between the comma and the big model.
 */
@Composable
fun HeroCard(state: StatusState, modifier: Modifier = Modifier, compact: Boolean = false, actions: StatusActions = StatusActions()) {
    when (val hero = state.hero) {
        is StatusState.Hero.Budget -> Headroom(hero.stats, modifier, compact)
        is StatusState.Hero.Progress -> Progress(hero.engine, state.modelName, modifier)
        StatusState.Hero.Waiting ->
            if (state.usb == UsbState.NeedsPermission) {
                AllowUsb(modifier, compact, actions.askUsb)
            } else {
                Waiting(state.waitingDescriptionRes, modifier, compact)
            }
        StatusState.Hero.NoModel -> NoModel(state, modifier, compact, actions)
        is StatusState.Hero.Failed -> Failed(hero.model, modifier, compact, actions.retry)
        StatusState.Hero.Stopped ->
            EmptyState(Icons.Filled.StopCircle, l10n(R.string.hero_stopped), modifier, compact = compact) {
                Button(onClick = actions.start) { Text(l10n(R.string.action_start)) }
            }
    }
}

@Composable
private fun Headroom(stats: Stats?, modifier: Modifier, compact: Boolean) {
    val colors = JetlinkTheme.colors
    val p99 = stats?.servedMs?.p99
    val tint = p99?.let { colors.tone(Room.forP99(it).tone) } ?: colors.secondaryText
    SummaryCard(l10n(R.string.card_headroom), Icons.Filled.Speed, tint, modifier, trailing = l10n(R.string.last_10s)) {
        Column(
            Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(if (compact) 12.dp else 20.dp),
        ) {
            HeadroomRing(
                p99,
                Modifier.widthIn(max = if (compact) 180.dp else 290.dp).fillMaxWidth(),
                lineWidth = if (compact) 14.dp else 22.dp,
                compact = compact,
            )
            FigureRow(
                listOf(
                    Triple("P99", p99, Color.Unspecified),
                    Triple(l10n(R.string.label_max), stats?.servedMs?.max, Color.Unspecified),
                ),
            )
        }
    }
}

@Composable
private fun Progress(engine: Engine, modelName: String?, modifier: Modifier) {
    val colors = JetlinkTheme.colors
    val title = if (engine.state == "loading") l10n(R.string.hero_loading) else l10n(R.string.hero_preparing)
    SummaryCard(title, Icons.Filled.Build, colors.info, modifier, trailing = Format.percent(engine.frac)) {
        Text(modelName ?: l10n(R.string.placeholder_model), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        LinearProgressIndicator(
            progress = { engine.frac.coerceIn(0.0, 1.0).toFloat() },
            modifier = Modifier.fillMaxWidth(),
            color = colors.info,
            trackColor = colors.info.copy(alpha = 0.2f),
        )
        Text(Format.stageName(engine.stage), style = MaterialTheme.typography.bodyMedium, color = colors.secondaryText)
    }
}

@Composable
private fun Waiting(descriptionRes: Int, modifier: Modifier, compact: Boolean) {
    val pulse = rememberInfiniteTransition(label = "waiting").animateFloat(
        initialValue = 1f,
        targetValue = 0.35f,
        animationSpec = infiniteRepeatable(tween(1000, easing = LinearEasing), RepeatMode.Reverse),
        label = "pulse",
    )
    EmptyState(
        Icons.Filled.Cable,
        l10n(R.string.summary_waiting),
        modifier,
        description = l10n(descriptionRes),
        compact = compact,
        iconAlpha = { pulse.value },
    )
}

/** Android has not let Jetlink use the comma yet. */
@Composable
fun AllowUsb(modifier: Modifier = Modifier, compact: Boolean = false, askAgain: () -> Unit) {
    EmptyState(
        Icons.Filled.Usb,
        l10n(R.string.summary_allow_usb),
        modifier,
        description = l10n(R.string.allow_usb_desc),
        compact = compact,
    ) {
        Button(onClick = askAgain) { Text(l10n(R.string.action_ask_again)) }
    }
}

@Composable
private fun NoModel(state: StatusState, modifier: Modifier, compact: Boolean, actions: StatusActions) {
    val unavailable = state.catalogUnavailable
    EmptyState(
        Icons.Outlined.Inventory2,
        l10n(R.string.summary_no_model),
        modifier,
        description = if (unavailable) l10n(R.string.no_model_catalog_error) else l10n(R.string.no_model_hint),
        compact = compact,
    ) {
        if (unavailable) {
            OutlinedButton(onClick = actions.refreshCatalog) { Text(l10n(R.string.action_try_again)) }
        } else {
            val row = state.defaultModel
            if (row != null && row.canUse) {
                Button(onClick = actions.useDefault) { Text(l10n(R.string.action_get_model, row.displayName)) }
            }
            TextButton(onClick = actions.openModels) { Text(l10n(R.string.action_browse_models)) }
        }
    }
}

/** What went wrong, in a line; the error itself is in Logs. */
@Composable
private fun Failed(model: Boolean, modifier: Modifier, compact: Boolean, retry: () -> Unit) {
    EmptyState(
        Icons.Outlined.ReportProblem,
        if (model) l10n(R.string.summary_model_failed) else l10n(R.string.hero_stopped),
        modifier,
        description = if (model) l10n(R.string.model_failed_desc) else l10n(R.string.stopped_see_logs),
        compact = compact,
    ) {
        OutlinedButton(onClick = retry) { Text(l10n(R.string.action_try_again)) }
    }
}

/** A line of trouble above the cards: Android's reason the comma could not be opened. */
@Composable
fun WarningBanner(text: String, modifier: Modifier = Modifier) {
    val colors = JetlinkTheme.colors
    Row(
        modifier.fillMaxWidth().cardBackground().padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Filled.Warning, contentDescription = null, tint = colors.warning, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(10.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
    }
}
