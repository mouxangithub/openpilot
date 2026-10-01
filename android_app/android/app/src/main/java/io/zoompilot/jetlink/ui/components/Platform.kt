package io.zoompilot.jetlink.ui.components

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import java.io.File
import java.net.Inet4Address

/** Hands `text` to another app: Messages, Notes, a mail. */
fun share(context: Context, text: String, subject: String) {
    val send = Intent(Intent.ACTION_SEND)
        .setType("text/plain")
        .putExtra(Intent.EXTRA_TEXT, text)
        .putExtra(Intent.EXTRA_SUBJECT, subject)
    context.startActivity(Intent.createChooser(send, null))
}

/** Hands a file in the app's cache to another app, through the app's FileProvider. */
fun shareFile(context: Context, file: File, type: String, subject: String) {
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
    val send = Intent(Intent.ACTION_SEND)
        .setType(type)
        .putExtra(Intent.EXTRA_STREAM, uri)
        .putExtra(Intent.EXTRA_SUBJECT, subject)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    send.clipData = ClipData.newRawUri(subject, uri)
    context.startActivity(Intent.createChooser(send, null))
}

fun copy(context: Context, label: String, text: String) {
    context.getSystemService(ClipboardManager::class.java)?.setPrimaryClip(ClipData.newPlainText(label, text))
}

/** The phone's IPv4 address on Wi-Fi, where a Mac's bench tools reach it; null off Wi-Fi. */
fun wifiAddress(context: Context): String? {
    val manager = context.getSystemService(ConnectivityManager::class.java) ?: return null
    return runCatching {
        val network = manager.activeNetwork ?: return null
        val capabilities = manager.getNetworkCapabilities(network) ?: return null
        if (!capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return null
        manager.getLinkProperties(network)?.let(::ipv4)
    }.getOrNull()
}

private fun ipv4(properties: LinkProperties): String? =
    properties.linkAddresses.map { it.address }.firstOrNull { it is Inet4Address && !it.isLoopbackAddress }?.hostAddress

/** The Wi-Fi address, kept current as the phone joins and leaves networks. */
@Composable
fun rememberWifiAddress(): String? {
    val context = LocalContext.current
    var address by remember { mutableStateOf(wifiAddress(context)) }
    DisposableEffect(context) {
        val manager: ConnectivityManager? = context.getSystemService(ConnectivityManager::class.java)
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onLinkPropertiesChanged(network: Network, linkProperties: LinkProperties) {
                address = ipv4(linkProperties) ?: wifiAddress(context)
            }

            override fun onLost(network: Network) {
                address = wifiAddress(context)
            }
        }
        val request = NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build()
        val registered = manager != null && runCatching { manager.registerNetworkCallback(request, callback) }.isSuccess
        onDispose {
            if (registered) runCatching { manager.unregisterNetworkCallback(callback) }
        }
    }
    return address
}
