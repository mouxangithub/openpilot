package io.zoompilot.jetlink.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.zoompilot.jetlink.server.Stages
import io.zoompilot.jetlink.server.Stats
import io.zoompilot.jetlink.ui.BUDGET_MS
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.FrameStage
import io.zoompilot.jetlink.ui.JetlinkTheme

/**
 * Where a frame's time goes: the average as one big number, the four stages
 * stacked on a bar as long as the budget, and each stage's time beside its
 * colour.
 */
@Composable
fun LatencyBreakdown(stats: Stats, modifier: Modifier = Modifier, compact: Boolean = false) {
    val colors = JetlinkTheme.colors
    val stages = stats.stagesMs ?: Stages()
    val mean = stats.servedMs?.mean ?: 0.0
    val description = "Average ${Format.ms(mean)}: " +
        FrameStage.entries.joinToString(", ") { "${it.title} ${Format.ms(it.value(stages))}" }
    Column(
        modifier.clearAndSetSemantics { contentDescription = description },
        verticalArrangement = Arrangement.spacedBy(if (compact) 12.dp else 16.dp),
    ) {
        Row {
            Text(
                Format.decimal(mean),
                fontSize = if (compact) 32.sp else 40.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.alignByBaseline(),
            )
            Spacer(Modifier.width(4.dp))
            Text(
                "ms avg",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = colors.secondaryText,
                modifier = Modifier.alignByBaseline(),
            )
        }
        StageBar(stages, p99 = stats.servedMs?.p99)
        if (compact) {
            FrameStage.entries.chunked(2).forEach { pair ->
                Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    pair.forEach { StageLegendRow(it, it.value(stages), Modifier.weight(1f)) }
                }
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                FrameStage.entries.forEach { StageLegendRow(it, it.value(stages)) }
            }
        }
    }
}

@Composable
private fun StageLegendRow(stage: FrameStage, ms: Double, modifier: Modifier = Modifier) {
    val colors = JetlinkTheme.colors
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(10.dp).clip(RoundedCornerShape(2.dp)).background(colors.stage(stage)))
        Spacer(Modifier.width(8.dp))
        Text(stage.title, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        Text(Format.decimal(ms), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.width(2.dp))
        Text("ms", style = MaterialTheme.typography.labelSmall, color = colors.secondaryText)
    }
}

/**
 * The stages' means stacked from zero over a track as long as the budget,
 * with the budget marked and labelled, and the P99 marked when it is known.
 */
@Composable
fun StageBar(stages: Stages, modifier: Modifier = Modifier, p99: Double? = null) {
    val colors = JetlinkTheme.colors
    val measurer = rememberTextMeasurer()
    val labelStyle = MaterialTheme.typography.labelSmall.copy(color = colors.secondaryText)
    val budgetStyle = labelStyle.copy(fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurface)
    val values = FrameStage.entries.map { it.value(stages) }
    val total = values.sum()
    val domain = maxOf(BUDGET_MS * 1.1, (p99 ?: 0.0) * 1.08, total * 1.08)
    val primary = MaterialTheme.colorScheme.onSurface
    Canvas(modifier.fillMaxWidth().height(40.dp)) {
        val thickness = 14.dp.toPx()
        val gap = 2.dp.toPx()
        val top = 4.dp.toPx()
        val x = { ms: Double -> (ms / domain * size.width).toFloat() }
        val radius = CornerRadius(4.dp.toPx())
        drawRoundRect(colors.track, topLeft = Offset(0f, top), size = Size(x(BUDGET_MS), thickness), cornerRadius = radius)
        var start = 0.0
        val present = FrameStage.entries.filter { it.value(stages) > 0 }
        present.forEachIndexed { index, stage ->
            val end = start + stage.value(stages)
            val last = index == present.size - 1
            val width = maxOf(2f, x(end) - x(start) - if (last) 0f else gap)
            drawRoundRect(
                colors.stage(stage),
                topLeft = Offset(x(start), top),
                size = Size(width, thickness),
                cornerRadius = if (index == 0 || last) radius else CornerRadius.Zero,
            )
            start = end
        }
        val budgetX = x(BUDGET_MS)
        drawLine(primary.copy(alpha = 0.55f), Offset(budgetX, top - 3.dp.toPx()), Offset(budgetX, top + thickness + 3.dp.toPx()), 1.dp.toPx())
        if (p99 != null && p99 > 0) {
            val p99X = x(p99)
            drawLine(primary, Offset(p99X, top - 3.dp.toPx()), Offset(p99X, top + thickness + 3.dp.toPx()), 2.dp.toPx())
        }
        val zero = measurer.measure("0", labelStyle)
        drawText(zero, topLeft = Offset(0f, top + thickness + 5.dp.toPx()))
        val budget = measurer.measure("${BUDGET_MS.toInt()} ms", budgetStyle)
        drawText(
            budget,
            topLeft = Offset(
                (budgetX - budget.size.width / 2f).coerceIn(0f, size.width - budget.size.width),
                top + thickness + 5.dp.toPx(),
            ),
        )
    }
}
