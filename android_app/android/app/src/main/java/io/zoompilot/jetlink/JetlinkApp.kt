package io.zoompilot.jetlink

import android.app.Application
import android.content.Context
import io.zoompilot.jetlink.device.DeviceMonitor
import io.zoompilot.jetlink.server.RunState
import io.zoompilot.jetlink.server.ServerController
import io.zoompilot.jetlink.server.ServerService
import io.zoompilot.jetlink.settings.Settings
import io.zoompilot.jetlink.usb.CommaUsb
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class JetlinkApp : Application() {
    lateinit var graph: AppGraph
        private set

    override fun onCreate() {
        super.onCreate()
        graph = AppGraph(this)
    }
}

/** The app's one of everything, for the life of the process. */
class AppGraph(context: Context) {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    val settings = Settings(context)
    val server = ServerController(context, scope)
    val usb = CommaUsb(context)
    val device = DeviceMonitor(context, scope)

    /**
     * Starts the server again with the current settings and hands it the
     * comma if one is plugged in; a stopped service starts, and starts it.
     */
    fun restartServer(context: Context) {
        if (server.runState.value == RunState.Stopped) {
            ServerService.start(context)
            return
        }
        scope.launch(Dispatchers.IO) {
            server.start(settings.values.value)
            usb.connect()
        }
    }
}

val Context.graph: AppGraph get() = (applicationContext as JetlinkApp).graph
