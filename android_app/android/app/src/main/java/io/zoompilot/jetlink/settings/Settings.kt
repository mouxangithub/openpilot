package io.zoompilot.jetlink.settings

import android.content.Context
import android.content.SharedPreferences
import io.zoompilot.jetlink.AppLocale
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Where the model runs, as the server's OrtProfile names it. */
enum class Processor(val id: String, val title: String) {
    /** The vision trunk on the NPU, the rest on the GPU: the Mac's split. */
    NpuGpu("htp", "NPU + GPU"),

    /** The whole model on the NPU, prepared as the iPhone's. */
    Npu("htp-whole", "NPU"),

    /** The whole model on the GPU, for when something else holds the NPU. */
    Gpu("gpu", "GPU"),

    /** The CPU: the emulator, and tests. Far over the budget with a real model. */
    Cpu("cpu", "CPU");

    companion object {
        fun of(id: String?): Processor? = entries.firstOrNull { it.id == id }
    }
}

/** The few things worth changing on a phone, kept in SharedPreferences. */
data class SettingsValues(
    /** Where bench tools such as `bench_link.py --host` reach the phone. */
    val port: Int = 5599,
    val processor: Processor = Processor.NpuGpu,
    /** The NPU held in burst mode between frames rather than let it settle. */
    val keepNpuAwake: Boolean = true,
    /** A CPU core kept busy between frames. */
    val keepCpuAwake: Boolean = false,
    /** The screen stays on while Jetlink is on screen. */
    val keepScreenOn: Boolean = true,
    /** The UI language; System follows the phone (the default). */
    val language: AppLocale = AppLocale.System,
)

class Settings(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
    private val state = MutableStateFlow(read())
    val values: StateFlow<SettingsValues> = state.asStateFlow()

    fun update(change: (SettingsValues) -> SettingsValues) {
        val next = change(state.value)
        prefs.edit()
            .putInt(PORT, next.port)
            .putString(PROCESSOR, next.processor.id)
            .putBoolean(KEEP_NPU_AWAKE, next.keepNpuAwake)
            .putBoolean(KEEP_CPU_AWAKE, next.keepCpuAwake)
            .putBoolean(KEEP_SCREEN_ON, next.keepScreenOn)
            .putString(LANGUAGE, next.language.id)
            .apply()
        state.value = next
    }

    private fun read(): SettingsValues {
        val defaults = SettingsValues(processor = defaultProcessor())
        val port = prefs.getInt(PORT, defaults.port)
        return SettingsValues(
            port = if (port in 1..65535) port else defaults.port,
            processor = Processor.of(prefs.getString(PROCESSOR, null)) ?: defaults.processor,
            keepNpuAwake = prefs.getBoolean(KEEP_NPU_AWAKE, defaults.keepNpuAwake),
            keepCpuAwake = prefs.getBoolean(KEEP_CPU_AWAKE, defaults.keepCpuAwake),
            keepScreenOn = prefs.getBoolean(KEEP_SCREEN_ON, defaults.keepScreenOn),
            language = AppLocale.of(prefs.getString(LANGUAGE, null)) ?: defaults.language,
        )
    }

    private companion object {
        const val PORT = "port"
        const val PROCESSOR = "processor"
        const val KEEP_NPU_AWAKE = "keepNpuAwake"
        const val KEEP_CPU_AWAKE = "keepCpuAwake"
        const val KEEP_SCREEN_ON = "keepScreenOn"
        const val LANGUAGE = "language"

        /** The CPU on the emulator, which has no NPU; the split elsewhere. */
        fun defaultProcessor(): Processor = if (Chip.isEmulator) Processor.Cpu else Processor.NpuGpu
    }
}
