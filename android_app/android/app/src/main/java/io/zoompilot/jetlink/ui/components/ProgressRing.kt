package io.zoompilot.jetlink.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

/**
 * A small determinate ring, as a store draws a download: with a stop square
 * inside while it can be stopped.
 */
@Composable
fun ProgressRing(frac: Double, stoppable: Boolean, modifier: Modifier = Modifier) {
    val color = MaterialTheme.colorScheme.primary
    val shown by animateFloatAsState(frac.coerceIn(0.02, 1.0).toFloat(), label = "download")
    Canvas(modifier.size(28.dp)) {
        val stroke = 3.dp.toPx()
        val side = size.minDimension - stroke
        val topLeft = Offset((size.width - side) / 2, (size.height - side) / 2)
        drawArc(color.copy(alpha = 0.2f), 0f, 360f, false, topLeft, Size(side, side), style = Stroke(stroke))
        drawArc(color, -90f, 360f * shown, false, topLeft, Size(side, side), style = Stroke(stroke, cap = StrokeCap.Round))
        if (stoppable) {
            val square = 9.dp.toPx()
            drawRoundRect(
                color,
                topLeft = Offset((size.width - square) / 2, (size.height - square) / 2),
                size = Size(square, square),
                cornerRadius = CornerRadius(2.dp.toPx()),
            )
        }
    }
}
