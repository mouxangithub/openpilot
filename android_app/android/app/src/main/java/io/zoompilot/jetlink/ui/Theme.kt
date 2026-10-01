package io.zoompilot.jetlink.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeviceThermostat
import androidx.compose.material.icons.filled.LocalFireDepartment
import androidx.compose.material.icons.filled.Thermostat
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector

/**
 * The colours Material's scheme has no slot for: the grouped screen and its
 * cards, the five tones, the card titles' tints and the frame stages.
 */
@Immutable
data class JetlinkColors(
    val grouped: Color,
    val card: Color,
    val secondaryText: Color,
    val tertiaryText: Color,
    /** An empty bar's track. */
    val track: Color,
    val good: Color,
    val warning: Color,
    val bad: Color,
    val info: Color,
    val teal: Color,
    val pink: Color,
    val purple: Color,
    val indigo: Color,
    val orange: Color,
    val gray: Color,
    val stageInput: Color,
    val stageModel: Color,
    val stageOther: Color,
    val stageSend: Color,
) {
    fun tone(tone: Tone): Color = when (tone) {
        Tone.Neutral -> secondaryText
        Tone.Info -> info
        Tone.Good -> good
        Tone.Warning -> warning
        Tone.Bad -> bad
    }

    /** The chart palette's four categorical slots, in stack order. */
    fun stage(stage: FrameStage): Color = when (stage) {
        FrameStage.Input -> stageInput
        FrameStage.Model -> stageModel
        FrameStage.Other -> stageOther
        FrameStage.Send -> stageSend
    }
}

/** openpilot's path green, deeper on a light screen. */
private val BrandLight = Color(0xFF16A34A)
private val BrandDark = Color(0xFF20F873)

private val LightColors = JetlinkColors(
    grouped = Color(0xFFF4F4F7),
    card = Color(0xFFFFFFFF),
    secondaryText = Color(0xFF6B6B73),
    tertiaryText = Color(0xFFA8A8B0),
    track = Color(0x14000000),
    good = BrandLight,
    warning = Color(0xFFF59E0B),
    bad = Color(0xFFEF4444),
    info = Color(0xFF2563EB),
    teal = Color(0xFF0D9488),
    pink = Color(0xFFDB2777),
    purple = Color(0xFF7C3AED),
    indigo = Color(0xFF4F46E5),
    orange = Color(0xFFEA580C),
    gray = Color(0xFF6B7280),
    stageInput = Color(0xFFEB6834),
    stageModel = Color(0xFF2A78D6),
    stageOther = Color(0xFF1BAF7A),
    stageSend = Color(0xFFEDA100),
)

private val DarkColors = JetlinkColors(
    grouped = Color(0xFF000000),
    card = Color(0xFF1C1C1E),
    secondaryText = Color(0xFF9D9DA6),
    tertiaryText = Color(0xFF5C5C63),
    track = Color(0x24FFFFFF),
    good = BrandDark,
    warning = Color(0xFFF59E0B),
    bad = Color(0xFFEF4444),
    info = Color(0xFF3B82F6),
    teal = Color(0xFF2DD4BF),
    pink = Color(0xFFF472B6),
    purple = Color(0xFFA78BFA),
    indigo = Color(0xFF818CF8),
    orange = Color(0xFFFB923C),
    gray = Color(0xFF9CA3AF),
    stageInput = Color(0xFFD95926),
    stageModel = Color(0xFF3987E5),
    stageOther = Color(0xFF199E70),
    stageSend = Color(0xFFC98500),
)

private val LightScheme = lightColorScheme(
    primary = BrandLight,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFD1FAE0),
    onPrimaryContainer = Color(0xFF052E16),
    secondary = Color(0xFF3F6B4F),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFD1FAE0),
    onSecondaryContainer = Color(0xFF052E16),
    background = LightColors.grouped,
    onBackground = Color(0xFF111113),
    surface = LightColors.grouped,
    onSurface = Color(0xFF111113),
    surfaceVariant = Color(0xFFE9E9EE),
    onSurfaceVariant = LightColors.secondaryText,
    surfaceContainerLowest = Color.White,
    surfaceContainerLow = Color.White,
    surfaceContainer = Color.White,
    surfaceContainerHigh = Color.White,
    surfaceContainerHighest = Color(0xFFE9E9EE),
    error = LightColors.bad,
    onError = Color.White,
    outline = Color(0xFFC7C7CC),
    outlineVariant = Color(0xFFE4E4E7),
)

private val DarkScheme = darkColorScheme(
    primary = BrandDark,
    onPrimary = Color(0xFF00210C),
    primaryContainer = Color(0xFF0F3D22),
    onPrimaryContainer = Color(0xFFBBF7D0),
    secondary = Color(0xFF9CD3AE),
    onSecondary = Color(0xFF00210C),
    secondaryContainer = Color(0xFF0F3D22),
    onSecondaryContainer = Color(0xFFBBF7D0),
    background = DarkColors.grouped,
    onBackground = Color(0xFFF4F4F5),
    surface = DarkColors.grouped,
    onSurface = Color(0xFFF4F4F5),
    surfaceVariant = Color(0xFF2C2C2E),
    onSurfaceVariant = DarkColors.secondaryText,
    surfaceContainerLowest = Color.Black,
    surfaceContainerLow = Color(0xFF121214),
    surfaceContainer = Color(0xFF121214),
    surfaceContainerHigh = Color(0xFF2C2C2E),
    surfaceContainerHighest = Color(0xFF3A3A3C),
    error = DarkColors.bad,
    onError = Color.White,
    outline = Color(0xFF48484A),
    outlineVariant = Color(0xFF2C2C2E),
)

private val LocalJetlinkColors = staticCompositionLocalOf { LightColors }

/** Material 3 in the brand's green, light or dark with the system; never the wallpaper's colours. */
@Composable
fun JetlinkTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalJetlinkColors provides if (dark) DarkColors else LightColors) {
        MaterialTheme(colorScheme = if (dark) DarkScheme else LightScheme, content = content)
    }
}

object JetlinkTheme {
    val colors: JetlinkColors
        @Composable @ReadOnlyComposable
        get() = LocalJetlinkColors.current
}

/** The thermometer for a phone's heat, a flame once it is critical. */
val Thermal.icon: ImageVector
    get() = when (this) {
        Thermal.Nominal, Thermal.Fair -> Icons.Filled.DeviceThermostat
        Thermal.Serious -> Icons.Filled.Thermostat
        Thermal.Critical -> Icons.Filled.LocalFireDepartment
    }
