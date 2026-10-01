package io.zoompilot.jetlink.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.zoompilot.jetlink.ui.JetlinkTheme

/**
 * An inset group, as a settings form sets them: a title, the rows on one
 * card, and a line of explanation under it.
 */
@Composable
fun FormSection(
    title: String?,
    modifier: Modifier = Modifier,
    footer: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(modifier.widthIn(max = ReadableWidth).fillMaxWidth()) {
        if (title != null) {
            Text(
                title,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                color = JetlinkTheme.colors.secondaryText,
                modifier = Modifier.padding(start = 16.dp, bottom = 6.dp),
            )
        }
        Column(Modifier.fillMaxWidth().cardBackground(), content = content)
        if (footer != null) {
            Box(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) { footer() }
        }
    }
}

/** The plain line under a section. */
@Composable
fun FormFooter(text: String) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = JetlinkTheme.colors.secondaryText)
}

/** The rule between two rows of a section. */
@Composable
fun RowDivider() {
    HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.outlineVariant)
}

/** A label and its value on the right. */
@Composable
fun ValueRow(label: String, value: String, modifier: Modifier = Modifier, valueColor: Color? = null) {
    Row(
        modifier.fillMaxWidth().heightIn(min = 48.dp).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
        Spacer(Modifier.width(12.dp))
        Text(
            value,
            style = MaterialTheme.typography.bodyLarge,
            color = valueColor ?: JetlinkTheme.colors.secondaryText,
            textAlign = TextAlign.End,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** A switch with its title and, when it needs one, a short line under it. */
@Composable
fun SwitchRow(title: String, checked: Boolean, onChange: (Boolean) -> Unit, supporting: String? = null) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(role = Role.Switch) { onChange(!checked) }
            .heightIn(min = 48.dp)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = MaterialTheme.typography.bodyLarge)
            if (supporting != null) {
                Text(supporting, style = MaterialTheme.typography.bodySmall, color = JetlinkTheme.colors.secondaryText)
            }
        }
        Spacer(Modifier.width(12.dp))
        Switch(checked = checked, onCheckedChange = null)
    }
}

/** A row that opens another screen, or does something. */
@Composable
fun ActionRow(title: String, onClick: () -> Unit, color: Color? = null, chevron: Boolean = true) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(role = Role.Button, onClick = onClick)
            .heightIn(min = 48.dp)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, style = MaterialTheme.typography.bodyLarge, color = color ?: Color.Unspecified, modifier = Modifier.weight(1f))
        if (chevron) {
            Icon(
                Icons.AutoMirrored.Filled.KeyboardArrowRight,
                contentDescription = null,
                tint = JetlinkTheme.colors.tertiaryText,
                modifier = Modifier.size(20.dp),
            )
        }
    }
}
