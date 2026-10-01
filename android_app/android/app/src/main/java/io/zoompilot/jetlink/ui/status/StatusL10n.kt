package io.zoompilot.jetlink.ui.status

import androidx.compose.runtime.Composable
import io.zoompilot.jetlink.R
import io.zoompilot.jetlink.device.DeviceHealth
import io.zoompilot.jetlink.l10n
import io.zoompilot.jetlink.ui.Thermal

/**
 * Composable-side translations of [StatusState]'s computed words. The state
 * keeps English strings for the notification (which cannot compose); these
 * re-derive the same words from resources, honouring the language override.
 */
object StatusL10n {
    /** The summary with the link it is over: "Connected over USB 3". */
    @Composable
    fun headline(state: StatusState): String {
        val summary = state.summary
        val medium = state.medium
        return if ((summary == StatusState.Summary.Connected || summary == StatusState.Summary.ConnectedSlow) && medium != null) {
            l10n(R.string.summary_connected_over, medium.title)
        } else {
            l10n(summary.titleRes)
        }
    }

    /** The line under the title: the summary and the model. */
    @Composable
    fun subtitle(state: StatusState): String =
        listOfNotNull(headline(state), state.modelName).joinToString(" · ")

    /** Under the Link tile: why there is none, or that a slow one costs frames. */
    @Composable
    fun linkNote(state: StatusState): String {
        val medium = state.medium
        return when {
            medium == null -> l10n(if (state.usb is io.zoompilot.jetlink.usb.UsbState.Attached) R.string.note_connecting else R.string.note_waiting)
            medium.slow -> l10n(R.string.note_slow_link)
            else -> l10n(R.string.summary_connected)
        }
    }

    /** "Throttling" when the heat costs frames, else the battery's temperature. */
    @Composable
    fun temperatureNote(health: DeviceHealth): String? {
        val thermal = Thermal.of(health.thermal)
        return if (thermal == Thermal.Serious || thermal == Thermal.Critical) {
            l10n(R.string.note_throttling)
        } else {
            health.batteryTemp?.let { l10n(R.string.note_battery_temp, Math.round(it)) }
        }
    }

    @Composable
    fun powerText(health: DeviceHealth): String = when {
        health.charging -> if ((health.batteryLevel ?: 0) >= 100) l10n(R.string.power_charged) else l10n(R.string.power_charging)
        health.batteryLevel == null -> l10n(R.string.power_unknown)
        health.powerSave -> l10n(R.string.power_battery_saver)
        else -> l10n(R.string.power_not_charging)
    }

    @Composable
    fun memoryNote(health: DeviceHealth): String? = when {
        health.availableMemory <= 0 -> null
        health.memoryTight -> l10n(R.string.memory_low)
        else -> l10n(R.string.memory_free)
    }

    @Composable
    fun thermalTitle(thermal: Thermal): String = l10n(
        when (thermal) {
            Thermal.Nominal -> R.string.thermal_normal
            Thermal.Fair -> R.string.thermal_warm
            Thermal.Serious -> R.string.thermal_hot
            Thermal.Critical -> R.string.thermal_critical
        },
    )
}
