package io.zoompilot.jetlink.settings

import android.os.Build

/**
 * The phone's SoC, and whether its NPU can run the model. QNN runs the
 * model in fp16 on the Hexagon NPU, which only v69 and later have: the
 * Snapdragon 8 Gen 1 and newer 8-series. The list is by Build.SOC_MODEL.
 */
object Chip {
    /** "SM8650", or the board name on older builds. */
    val model: String
        get() = Build.SOC_MODEL.takeIf { it.isNotBlank() && it != Build.UNKNOWN } ?: Build.BOARD

    val manufacturer: String get() = Build.SOC_MANUFACTURER

    val isQualcomm: Boolean
        get() = manufacturer.equals("QTI", ignoreCase = true) || manufacturer.equals("Qualcomm", ignoreCase = true)

    val isEmulator: Boolean
        get() = Build.HARDWARE.contains("ranchu") || Build.HARDWARE.contains("goldfish") || Build.PRODUCT.contains("sdk")

    /** Known Snapdragons, by SoC model: name, Hexagon generation. */
    private val known = mapOf(
        "SM8350" to ("Snapdragon 888" to 68),
        "SM8450" to ("Snapdragon 8 Gen 1" to 69),
        "SM8475" to ("Snapdragon 8+ Gen 1" to 69),
        "SM8550" to ("Snapdragon 8 Gen 2" to 73),
        "SM8650" to ("Snapdragon 8 Gen 3" to 75),
        "SM8635" to ("Snapdragon 8s Gen 3" to 73),
        "SM8750" to ("Snapdragon 8 Elite" to 79),
        "SM8850" to ("Snapdragon 8 Elite Gen 5" to 81),
    )

    /** "Snapdragon 8 Gen 3", or the SoC model when this list does not know it. */
    val name: String get() = known[model]?.first ?: model

    /** The Hexagon NPU's generation, when known. */
    val hexagon: Int? get() = known[model]?.second

    /** How well this phone should do, before a benchmark says for sure. */
    enum class Expectation { Recommended, Possible, TooOld, NoNpu }

    val expectation: Expectation
        get() {
            if (!isQualcomm) return Expectation.NoNpu
            val v = hexagon ?: return Expectation.Possible
            return when {
                v >= 75 -> Expectation.Recommended
                v >= 69 -> Expectation.Possible
                else -> Expectation.TooOld
            }
        }
}
