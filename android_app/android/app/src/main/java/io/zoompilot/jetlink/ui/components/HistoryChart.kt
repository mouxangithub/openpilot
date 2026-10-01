package io.zoompilot.jetlink.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import io.zoompilot.jetlink.server.HistorySample
import io.zoompilot.jetlink.ui.BUDGET_MS
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.HISTORY_SECONDS
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.Room

/** Seconds per bar: 24 bars over two minutes, wide enough to read on a phone. */
private const val BUCKET_SECONDS = 5.0

/**
 * The last two minutes as a trend: a rounded bar for every five seconds, as
 * tall as the slowest 1% of its frames and coloured by the room it left, a
 * thin whisker up to its slowest frame, under a dashed line at the 50 ms budget.
 */
@Composable
fun HistoryChart(history: List<HistorySample>, modifier: Modifier = Modifier) {
    val colors = JetlinkTheme.colors
    val buckets = remember(history) { Format.historyBuckets(history, BUCKET_SECONDS) }
    val measurer = rememberTextMeasurer()
    val labelStyle = MaterialTheme.typography.labelSmall.copy(color = colors.secondaryText)
    val budgetStyle = labelStyle.copy(fontWeight = FontWeight.SemiBold)
    val grid = colors.secondaryText.copy(alpha = 0.25f)
    val rule = colors.secondaryText.copy(alpha = 0.8f)
    val worst = buckets.maxOfOrNull { it.p99 } ?: 0.0
    val top = maxOf(BUDGET_MS * 1.2, worst * 1.1)
    val over = buckets.count { it.p99 > BUDGET_MS }
    val description = "Last two minutes: worst P99 ${Format.ms(worst)}, $over of ${buckets.size} five-second spans over budget."
    Canvas(modifier.fillMaxWidth().height(150.dp).semantics { contentDescription = description }) {
        val axisBand = 40.dp.toPx()
        val labelBand = 18.dp.toPx()
        val plotWidth = size.width - axisBand
        val plotHeight = size.height - labelBand
        val start = -HISTORY_SECONDS.toDouble()
        val end = BUCKET_SECONDS / 2
        val x = { seconds: Double -> ((seconds - start) / (end - start) * plotWidth).toFloat() }
        val y = { ms: Double -> (plotHeight - (ms.coerceIn(0.0, top) / top) * plotHeight).toFloat() }

        for (ms in listOf(0.0, 25.0, BUDGET_MS)) {
            val at = y(ms)
            if (ms == BUDGET_MS) {
                drawLine(
                    rule, Offset(0f, at), Offset(plotWidth, at), 1.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 4.dp.toPx())),
                )
            } else {
                drawLine(grid, Offset(0f, at), Offset(plotWidth, at), 0.5.dp.toPx())
            }
            val label = measurer.measure(if (ms == BUDGET_MS) "${ms.toInt()} ms" else "${ms.toInt()}", if (ms == BUDGET_MS) budgetStyle else labelStyle)
            drawText(label, topLeft = Offset(plotWidth + 6.dp.toPx(), (at - label.size.height / 2f).coerceIn(0f, size.height - label.size.height)))
        }

        val barWidth = 7.dp.toPx()
        val whisker = 2.dp.toPx()
        for (bucket in buckets) {
            val center = x(-bucket.age)
            val color = colors.tone(Room.forP99(bucket.p99).tone)
            if (bucket.max > bucket.p99) {
                drawRect(
                    color.copy(alpha = 0.4f),
                    topLeft = Offset(center - whisker / 2, y(bucket.max)),
                    size = Size(whisker, y(bucket.p99) - y(bucket.max)),
                )
            }
            val barTop = minOf(y(bucket.p99), plotHeight - barWidth)
            drawRoundRect(
                color,
                topLeft = Offset(center - barWidth / 2, barTop),
                size = Size(barWidth, plotHeight - barTop),
                cornerRadius = CornerRadius(barWidth / 2),
            )
        }

        val labelTop = plotHeight + 4.dp.toPx()
        val oldest = measurer.measure("2 min", labelStyle)
        drawText(oldest, topLeft = Offset(0f, labelTop))
        val middle = measurer.measure("1 min", labelStyle)
        drawText(middle, topLeft = Offset(x(-60.0) - middle.size.width / 2f, labelTop))
        val now = measurer.measure("Now", labelStyle)
        drawText(now, topLeft = Offset(plotWidth - now.size.width, labelTop))
    }
}
