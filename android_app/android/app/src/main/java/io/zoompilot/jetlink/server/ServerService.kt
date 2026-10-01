package io.zoompilot.jetlink.server

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import io.zoompilot.jetlink.MainActivity
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.graph
import io.zoompilot.jetlink.settings.SettingsValues
import io.zoompilot.jetlink.ui.status.StatusState
import io.zoompilot.jetlink.usb.CommaUsb
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Runs the server while Jetlink is on: a foreground service of the
 * connectedDevice type, so it keeps serving the comma with the screen off
 * and the app in the background, for a whole drive. It holds the comma's USB
 * connection, a wake lock while a comma is connected, and a notification
 * that says how things stand.
 */
class ServerService : LifecycleService() {
    private val graph get() = applicationContext.graph
    private var wakeLock: PowerManager.WakeLock? = null

    private val usbEvents = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            // Detaching waits for the server to let the descriptor go: not on the main thread.
            val pending = goAsync()
            graph.scope.launch(Dispatchers.IO) {
                try {
                    when (intent.action) {
                        UsbManager.ACTION_USB_DEVICE_ATTACHED, CommaUsb.ACTION_PERMISSION -> graph.usb.connect()
                        UsbManager.ACTION_USB_DEVICE_DETACHED ->
                            graph.usb.detached(IntentCompat.getParcelableExtra(intent, UsbManager.EXTRA_DEVICE, UsbDevice::class.java))
                    }
                } finally {
                    pending.finish()
                }
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        createChannel()
        startForeground(NOTIFICATION_ID, notification("Starting"), ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        val filter = IntentFilter().apply {
            addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED)
            addAction(UsbManager.ACTION_USB_DEVICE_DETACHED)
            addAction(CommaUsb.ACTION_PERMISSION)
        }
        ContextCompat.registerReceiver(this, usbEvents, filter, ContextCompat.RECEIVER_NOT_EXPORTED)

        // The server restarts when a setting it runs with changes, as on the iPhone.
        lifecycleScope.launch {
            graph.settings.values.map(::serverSettings).distinctUntilChanged().collectLatest {
                graph.server.start(graph.settings.values.value)
                withContext(Dispatchers.IO) { graph.usb.connect() }
            }
        }
        lifecycleScope.launch {
            // the line under the Status title
            combine(graph.server.runState, graph.server.snapshot, graph.usb.usb) { run, snapshot, usb ->
                StatusState(run, snapshot, usb = usb).subtitle to snapshot.connected
            }.distinctUntilChanged().collectLatest { (text, connected) ->
                getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
                holdWakeLock(connected)
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action) {
            ACTION_STOP -> {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
            ACTION_USB -> graph.scope.launch(Dispatchers.IO) { graph.usb.connect() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        unregisterReceiver(usbEvents)
        holdWakeLock(false)
        graph.scope.launch(Dispatchers.IO) {
            graph.usb.disconnect()
            graph.server.stop()
        }
        super.onDestroy()
    }

    /** Held while a comma is connected: frames are not user input, and the CPU must not sleep between them. */
    private fun holdWakeLock(hold: Boolean) {
        val held = wakeLock
        if (hold && held == null) {
            wakeLock = getSystemService(PowerManager::class.java)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "jetlink:serving")
                .apply { setReferenceCounted(false); acquire() }
        } else if (!hold && held != null) {
            held.release()
            wakeLock = null
        }
    }

    private fun createChannel() {
        val channel = NotificationChannel(CHANNEL, "Server", NotificationManager.IMPORTANCE_LOW).apply {
            description = "Shows while Jetlink serves the comma"
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val stop = PendingIntent.getService(
            this, 1, Intent(this, ServerService::class.java).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Jetlink")
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(true)
            .setSilent(true)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .addAction(0, "Stop", stop)
            .build()
    }

    companion object {
        const val ACTION_STOP = "io.zoompilot.jetlink.STOP"
        const val ACTION_USB = "io.zoompilot.jetlink.USB"
        private const val CHANNEL = "server"
        private const val NOTIFICATION_ID = 1

        fun start(context: Context, action: String? = null) {
            ContextCompat.startForegroundService(context, Intent(context, ServerService::class.java).setAction(action))
        }

        /** The settings the server runs with; the screen's own do not restart it. */
        private fun serverSettings(values: SettingsValues) = values.copy(keepScreenOn = false)
    }
}
