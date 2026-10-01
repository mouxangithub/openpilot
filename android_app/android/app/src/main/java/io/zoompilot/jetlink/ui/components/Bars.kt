package io.zoompilot.jetlink.ui.components

import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.RowScope
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.font.FontWeight
import io.zoompilot.jetlink.ui.JetlinkTheme

/** A screen pushed over a tab: its title, a back arrow, and its own actions. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PushedScreen(
    title: String,
    back: () -> Unit,
    actions: @Composable RowScope.() -> Unit = {},
    content: @Composable (PaddingValues) -> Unit,
) {
    Scaffold(
        containerColor = JetlinkTheme.colors.grouped,
        topBar = {
            TopAppBar(
                title = { Text(title, fontWeight = FontWeight.SemiBold) },
                navigationIcon = {
                    IconButton(onClick = back) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
                },
                actions = actions,
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = JetlinkTheme.colors.grouped,
                    scrolledContainerColor = JetlinkTheme.colors.grouped,
                ),
            )
        },
        content = content,
    )
}
