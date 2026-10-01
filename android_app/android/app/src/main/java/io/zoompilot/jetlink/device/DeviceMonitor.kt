package io.zoompilot.jetlink.device

import android.app.ActivityManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.PowerManager
import androidx.core.content.ContextCompat
import io.zoompilot.jetlink.server.Native
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.asExecutor
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.stateIn
import kotlin.math.roundToInt

/** The phone's own state, which is what slows a model down first. */
data class DeviceHealth(
    /** "nominal", "fair", "serious" or "critical", as the benchmark names them. */
    val thermal: String = "nominal",
    /** Android's thermal headroom: 1.0 is where it starts throttling. Null when unknown. */
    val headroom: Float? = null,
    /** The battery's temperature, °C. */
    val batteryTemp: Float? = null,
    val batteryLevel: Int? = null,
    val charging: Boolean = false,
    val powerSave: Boolean = false,
    val availableMemory: Long = 0,
    val lowMemory: Boolean = false,
) {
    /** Under 1 GB free a model may not fit to prepare, as on the iPhone. */
    val memoryTight: Boolean get() = availableMemory in 1 until 1_000_000_000L || lowMemory
}

/**
 * Battery, heat and memory, read once a second while a screen shows them,
 * and the thermal state told to the server as it changes, for its benchmark
 * reports.
 */
class DeviceMonitor(context: Context, scope: CoroutineScope) {
    private val power = context.getSystemService(PowerManager::class.java)
    private val activity = context.getSystemService(ActivityManager::class.java)

    @Volatile private var battery: Intent? = null

    init {
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                battery = intent
            }
        }
        battery = ContextCompat.registerReceiver(
            context, receiver, IntentFilter(Intent.ACTION_BATTERY_CHANGED), ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        // Called at once with the current status, then on each change.
        power.addThermalStatusListener(Dispatchers.Default.asExecutor()) { Native.reportThermal(thermalLabel(it)) }
    }

    val health: StateFlow<DeviceHealth> = flow {
        while (true) {
            emit(read())
            delay(1000)
        }
    }.flowOn(Dispatchers.Default).stateIn(scope, SharingStarted.WhileSubscribed(5_000), DeviceHealth())

    private fun read(): DeviceHealth {
        val memory = ActivityManager.MemoryInfo().also(activity::getMemoryInfo)
        val intent = battery
        val level = intent?.let {
            val raw = it.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            val scale = it.getIntExtra(BatteryManager.EXTRA_SCALE, 100)
            if (raw >= 0 && scale > 0) raw * 100 / scale else null
        }
        val plugged = (intent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
        val tenths = intent?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE) ?: Int.MIN_VALUE
        // The headroom forecast is rate limited to about once a second.
        val headroom = power.getThermalHeadroom(10).takeUnless { it.isNaN() }
        // Rounded to what the tiles show, so a reading that moves by bytes is not a new state.
        return DeviceHealth(
            thermal = thermalLabel(power.currentThermalStatus),
            headroom = headroom?.let { (it * 100).roundToInt() / 100f },
            batteryTemp = if (tenths != Int.MIN_VALUE) tenths / 10f else null,
            batteryLevel = level,
            charging = plugged,
            powerSave = power.isPowerSaveMode,
            availableMemory = memory.availMem / MEMORY_STEP * MEMORY_STEP,
            lowMemory = memory.lowMemory,
        )
    }

    companion object {
        private const val MEMORY_STEP = 100_000_000L

        /** PowerManager's thermal status in the benchmark's four words. */
        fun thermalLabel(status: Int): String = when (status) {
            PowerManager.THERMAL_STATUS_NONE, PowerManager.THERMAL_STATUS_LIGHT -> "nominal"
            PowerManager.THERMAL_STATUS_MODERATE -> "fair"
            PowerManager.THERMAL_STATUS_SEVERE -> "serious"
            else -> "critical"
        }
    }
}
