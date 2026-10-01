package io.zoompilot.jetlink.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Dangerous
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.zoompilot.jetlink.ui.BUDGET_MS
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.Room
import kotlin.math.abs

/** The ring's share of a circle; the gap sits at the bottom. */
private const val SWEEP = 270f

/**
 * The frame budget as a gauge: a 270° track as long as the 50 ms the comma
 * gives each frame, filled to the P99 frame time, with the room left as the
 * one big number inside. One number and one state, for a glance at a phone in
 * a car mount. `p99` null draws an empty track: no frames yet.
 */
@Composable
fun HeadroomRing(p99: Double?, modifier: Modifier = Modifier, lineWidth: Dp = 22.dp, compact: Boolean = false) {
    val colors = JetlinkTheme.colors
    val room = p99?.let(Room::forP99)
    val tint = room?.let { colors.tone(it.tone) } ?: colors.secondaryText
    val fraction by animateFloatAsState(
        targetValue = p99?.let { (it / BUDGET_MS).coerceIn(0.0, 1.0).toFloat() } ?: 0f,
        animationSpec = tween(600),
        label = "headroom",
    )
    val description = if (p99 == null || room == null) {
        "No frames yet"
    } else {
        "${Format.headroomText(p99)} of ${BUDGET_MS.toInt()} milliseconds. ${room.title}."
    }
    Box(
        modifier.aspectRatio(1f).clearAndSetSemantics { contentDescription = description },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = lineWidth.toPx()
            val side = size.minDimension - stroke
            val topLeft = Offset((size.width - side) / 2, (size.height - side) / 2)
            val arc = Size(side, side)
            drawArc(
                color = tint.copy(alpha = if (p99 == null) 0.15f else 0.22f),
                startAngle = 135f,
                sweepAngle = SWEEP,
                useCenter = false,
                topLeft = topLeft,
                size = arc,
                style = Stroke(width = stroke, cap = StrokeCap.Round),
            )
            if (p99 != null) {
                drawArc(
                    color = tint,
                    startAngle = 135f,
                    sweepAngle = SWEEP * fraction.coerceAtLeast(0.001f),
                    useCenter = false,
                    topLeft = topLeft,
                    size = arc,
                    style = Stroke(width = stroke, cap = StrokeCap.Round),
                )
            }
        }
        Column(
            Modifier.padding(horizontal = lineWidth * 1.5f),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            val big = if (compact) 40.sp else 64.sp
            if (p99 != null && room != null) {
                val headroom = BUDGET_MS - p99
                Row {
                    Text(
                        Format.decimal(abs(headroom)),
                        fontSize = big,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        modifier = Modifier.alignByBaseline(),
                    )
                    Spacer(Modifier.width(4.dp))
                    Text(
                        if (headroom >= 0) "ms" else "ms over",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = colors.secondaryText,
                        maxLines = 1,
                        modifier = Modifier.alignByBaseline(),
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(roomIcon(room), contentDescription = null, tint = tint, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(4.dp))
                    Text(room.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = tint)
                }
            } else {
                Text("--", fontSize = big, fontWeight = FontWeight.Bold, color = colors.tertiaryText)
                Text(
                    "No Frames",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = colors.secondaryText,
                )
            }
        }
        Text(
            "${BUDGET_MS.toInt()} ms",
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            color = colors.secondaryText,
            modifier = Modifier.align(Alignment.BottomCenter),
        )
    }
}

fun roomIcon(room: Room): ImageVector = when (room) {
    Room.Plenty -> Icons.Filled.CheckCircle
    Room.Tight -> Icons.Filled.Warning
    Room.Over -> Icons.Filled.Dangerous
}
