package io.zoompilot.jetlink.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.components.ActionRow
import io.zoompilot.jetlink.ui.components.CardSpacing
import io.zoompilot.jetlink.ui.components.FormFooter
import io.zoompilot.jetlink.ui.components.FormSection
import io.zoompilot.jetlink.ui.components.PushedScreen
import io.zoompilot.jetlink.ui.components.RowDivider

private const val GUIDE = "https://github.com/zoompilot/jetlink/blob/main/docs/android-app.md#connect-the-comma"

private val steps = listOf(
    R.string.connect_step_1,
    R.string.connect_step_2,
    R.string.connect_step_3,
    R.string.connect_step_4,
    R.string.connect_step_5,
    R.string.connect_step_6,
)

private val notes = listOf(
    R.string.connect_note_1,
    R.string.connect_note_2,
)

/** How the comma and the phone meet, in a few steps for a reader standing at the car. */
@Composable
fun ConnectHelpScreen(back: () -> Unit) {
    val uriHandler = LocalUriHandler.current
    PushedScreen(l10n(R.string.help_connect), back) { padding ->
        Column(
            Modifier
                .padding(padding)
                .consumeWindowInsets(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = CardSpacing)
                .padding(top = 8.dp, bottom = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            FormSection(
                null,
                footer = { FormFooter(l10n(R.string.connect_footer_otg)) },
            ) {
                steps.forEachIndexed { index, step ->
                    if (index > 0) RowDivider()
                    Step(index + 1, l10n(step))
                }
            }
            FormSection(
                l10n(R.string.section_good_to_know),
                footer = { FormFooter(l10n(R.string.connect_footer_usb3)) },
            ) {
                notes.forEachIndexed { index, note ->
                    if (index > 0) RowDivider()
                    Text(l10n(note), style = MaterialTheme.typography.bodyLarge, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp))
                }
            }
            FormSection(null) {
                ActionRow(l10n(R.string.action_learn_more), { runCatching { uriHandler.openUri(GUIDE) } }, color = MaterialTheme.colorScheme.primary, chevron = false)
            }
        }
    }
}

@Composable
private fun Step(number: Int, text: String) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp).semantics(mergeDescendants = true) {},
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            number.toString(),
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.SemiBold,
            color = JetlinkTheme.colors.secondaryText,
            textAlign = TextAlign.End,
            modifier = Modifier.width(18.dp),
        )
        Text(text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(start = 12.dp))
    }
}

@Preview(showBackground = true, heightDp = 800)
@Composable
private fun ConnectHelpPreview() {
    JetlinkTheme { ConnectHelpScreen(back = {}) }
}
