package io.zoompilot.jetlink.ui.logs

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import io.zoompilot.jetlink.AppGraph
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.ui.Format
import io.zoompilot.jetlink.ui.JetlinkTheme
import io.zoompilot.jetlink.ui.LogLevel
import io.zoompilot.jetlink.ui.components.CardSpacing
import io.zoompilot.jetlink.ui.components.PushedScreen
import io.zoompilot.jetlink.ui.components.shareFile
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * What the server and the app have logged, newest at the bottom, following
 * new lines until the reader scrolls up. Warnings orange, errors red.
 */
@Composable
fun LogsScreen(graph: AppGraph, back: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val lines by graph.server.logs.collectAsStateWithLifecycle()
    LogsContent(
        lines = lines,
        back = back,
        share = {
            scope.launch {
                val file = withContext(Dispatchers.IO) { logFile(context, lines) }
                shareFile(context, file, "text/plain", "Jetlink Logs")
            }
        },
        clear = graph.server::clearLogs,
    )
}

/** The log as a file to share: an intent's text would have to fit one Binder transaction. */
private fun logFile(context: Context, lines: List<String>): File =
    File(context.cacheDir, "logs").apply { mkdirs() }.resolve("jetlink.log").apply { writeText(lines.joinToString("\n", postfix = "\n")) }

@Composable
fun LogsContent(lines: List<String>, back: () -> Unit, share: () -> Unit, clear: () -> Unit) {
    val colors = JetlinkTheme.colors
    val list = rememberLazyListState()
    var follow by remember { mutableStateOf(true) }
    // While the reader scrolls, follow new lines only from the bottom.
    LaunchedEffect(list) {
        snapshotFlow { list.isScrollInProgress to list.canScrollForward }.collect { (scrolling, more) ->
            if (scrolling) follow = !more
        }
    }
    LaunchedEffect(lines.size) {
        if (follow && lines.isNotEmpty()) list.scrollToItem(lines.lastIndex)
    }
    PushedScreen(
        l10n(R.string.help_logs),
        back,
        actions = {
            IconButton(onClick = share, enabled = lines.isNotEmpty()) { Icon(Icons.Filled.Share, contentDescription = l10n(R.string.content_desc_share)) }
            IconButton(onClick = clear, enabled = lines.isNotEmpty()) { Icon(Icons.Filled.Delete, contentDescription = l10n(R.string.content_desc_clear)) }
        },
    ) { padding ->
        Box(Modifier.padding(padding).consumeWindowInsets(padding).fillMaxSize()) {
            if (lines.isEmpty()) {
                Column(
                    Modifier.align(Alignment.Center),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Icon(Icons.Filled.Description, contentDescription = null, tint = colors.secondaryText, modifier = Modifier.size(48.dp))
                    Text(l10n(R.string.no_logs), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                }
            } else {
                SelectionContainer {
                    LazyColumn(
                        Modifier.fillMaxSize(),
                        state = list,
                        contentPadding = PaddingValues(horizontal = CardSpacing, vertical = 8.dp),
                        verticalArrangement = Arrangement.spacedBy(2.dp),
                    ) {
                        itemsIndexed(lines) { _, line ->
                            Text(
                                line,
                                fontFamily = FontFamily.Monospace,
                                fontSize = 11.sp,
                                lineHeight = 14.sp,
                                color = when (Format.logLevel(line)) {
                                    LogLevel.Error -> colors.bad
                                    LogLevel.Warning -> colors.warning
                                    LogLevel.Info -> Color.Unspecified
                                },
                                modifier = Modifier.fillMaxWidth(),
                            )
                        }
                    }
                }
            }
        }
    }
}

@Preview(showBackground = true, heightDp = 500)
@Composable
private fun LogsPreview() {
    JetlinkTheme {
        LogsContent(
            lines = listOf(
                "2026-09-27 12:53:20,114 INFO jetlink.server: listening on port 5599",
                "2026-09-27 12:53:22,871 INFO jetlink.link: comma connected over USB 3",
                "2026-09-27 12:53:24,982 WARNING jetlink.engine: frame 1841 took 61.2 ms",
                "2026-09-27 12:53:25,003 ERROR   jetlink.link: the device went away",
            ),
            back = {},
            share = {},
            clear = {},
        )
    }
}
