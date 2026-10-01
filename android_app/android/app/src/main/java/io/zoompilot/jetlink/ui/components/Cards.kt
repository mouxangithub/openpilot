package io.zoompilot.jetlink.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.JetlinkTheme

/** The corner every card shares, so they read as one family. */
val CardShape = RoundedCornerShape(24.dp)

/** The space between cards, and the screen's side margin. */
val CardSpacing = 16.dp

/** The widest one column of cards grows, so a tablet keeps a readable line. */
val ReadableWidth = 672.dp

/** A card's rounded background, for content that is not a SummaryCard. */
@Composable
fun Modifier.cardBackground(): Modifier = clip(CardShape).background(JetlinkTheme.colors.card)

/**
 * A card in the Health style: a tinted icon and title, what it covers on the
 * right, then the content.
 */
@Composable
fun SummaryCard(
    title: String,
    icon: ImageVector,
    tint: Color,
    modifier: Modifier = Modifier,
    trailing: String? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier.fillMaxWidth().cardBackground().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text(
                title,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = tint,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            if (trailing != null) {
                Text(trailing, style = MaterialTheme.typography.bodyMedium, color = JetlinkTheme.colors.secondaryText)
            }
        }
        content()
    }
}

/** One number with its unit under a tinted title: the Health app's metric tile. */
@Composable
fun MetricTile(
    title: String,
    icon: ImageVector,
    tint: Color,
    value: String,
    modifier: Modifier = Modifier,
    unit: String? = null,
    note: String? = null,
    noteColor: Color? = null,
) {
    val colors = JetlinkTheme.colors
    Column(modifier.cardBackground().padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
            Text(
                title,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = tint,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Row {
            Text(
                value,
                fontSize = 28.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.alignByBaseline().weight(1f, fill = false),
            )
            if (unit != null) {
                Spacer(Modifier.width(3.dp))
                Text(
                    unit,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = colors.secondaryText,
                    maxLines = 1,
                    modifier = Modifier.alignByBaseline(),
                )
            }
        }
        Text(
            note ?: " ",
            style = MaterialTheme.typography.bodySmall,
            color = noteColor ?: colors.secondaryText,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** Tiles two to a row, as tall as the taller one; give each `Modifier.weight(1f).fillMaxHeight()`. */
@Composable
fun MetricRow(modifier: Modifier = Modifier, content: @Composable RowScope.() -> Unit) {
    Row(
        modifier.fillMaxWidth().height(IntrinsicSize.Min),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        content = content,
    )
}

/** The modifier a tile in a MetricRow takes. */
fun RowScope.tile(): Modifier = Modifier.weight(1f).fillMaxHeight()

/** A title over a group of cards, with a word or two on the right when there is something to say. */
@Composable
fun SectionHeader(title: String, modifier: Modifier = Modifier, detail: String? = null) {
    Row(
        modifier.fillMaxWidth().padding(top = 8.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        Text(
            title,
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.weight(1f).alignByBaseline(),
        )
        if (detail != null) {
            Text(
                detail,
                style = MaterialTheme.typography.bodyMedium,
                color = JetlinkTheme.colors.secondaryText,
                modifier = Modifier.alignByBaseline(),
            )
        }
    }
}

/** Nothing to show yet, and why: an icon, a title, a line, and what to do. */
@Composable
fun EmptyState(
    icon: ImageVector,
    title: String,
    modifier: Modifier = Modifier,
    description: String? = null,
    compact: Boolean = false,
    /** Read while drawing, so an animated alpha does not recompose the card. */
    iconAlpha: () -> Float = { 1f },
    actions: (@Composable ColumnScope.() -> Unit)? = null,
) {
    val colors = JetlinkTheme.colors
    Column(
        modifier.fillMaxWidth().cardBackground().padding(horizontal = 24.dp, vertical = if (compact) 20.dp else 36.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = colors.secondaryText,
            modifier = Modifier.size(if (compact) 36.dp else 48.dp).graphicsLayer { alpha = iconAlpha() },
        )
        Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center)
        if (description != null) {
            Text(
                description,
                style = MaterialTheme.typography.bodyMedium,
                color = colors.secondaryText,
                textAlign = TextAlign.Center,
            )
        }
        if (actions != null) {
            Column(
                Modifier.padding(top = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(4.dp),
                content = actions,
            )
        }
    }
}

/** A label over a number of milliseconds, the dashboards' unit of account. */
@Composable
fun Figure(label: String, ms: Double?, modifier: Modifier = Modifier, tone: Color = Color.Unspecified) {
    val colors = JetlinkTheme.colors
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = colors.secondaryText)
        Row {
            Text(
                ms?.let(Format::decimal) ?: "--",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
                color = tone,
                modifier = Modifier.alignByBaseline(),
            )
            Spacer(Modifier.width(2.dp))
            Text(
                "ms",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = colors.secondaryText,
                modifier = Modifier.alignByBaseline(),
            )
        }
    }
}

/** Figures side by side, with a thin rule between them. */
@Composable
fun FigureRow(figures: List<Triple<String, Double?, Color>>, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        figures.forEachIndexed { index, (label, ms, tone) ->
            if (index > 0) VerticalDivider(Modifier.height(32.dp))
            Figure(label, ms, Modifier.weight(1f), tone)
        }
    }
}

/** A small capsule beside a name: "Default", "Comma". */
@Composable
fun Tag(text: String, color: Color, modifier: Modifier = Modifier) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall,
        fontWeight = FontWeight.Medium,
        color = color,
        maxLines = 1,
        modifier = modifier
            .clip(CircleShape)
            .background(color.copy(alpha = 0.14f))
            .padding(horizontal = 6.dp, vertical = 1.dp),
    )
}
