package io.zoompilot.jetlink

import android.content.Context
import android.content.res.Configuration
import java.util.Locale

/**
 * The app's languages. `System` follows the phone's locale (the default and
 * the Android behaviour), and the two manual choices let a phone whose system
 * language is something else read Jetlink in a known one. Adding a language
 * is: a new enum value, a `values-<code>` resource directory, and an entry in
 * `L10n.localeFor`.
 */
enum class AppLocale(val id: String, val displayName: String) {
    System("system", "跟随系统 / System"),
    English("en", "English"),
    Chinese("zh", "中文");

    companion object {
        fun of(id: String?): AppLocale? = entries.firstOrNull { it.id == id }

        /** The Locale a choice implies; System resolves to the device's. */
        fun localeFor(locale: AppLocale): Locale = when (locale) {
            System -> Locale.getDefault()
            English -> Locale.forLanguageTag("en")
            Chinese -> Locale.forLanguageTag("zh-rCN")
        }

        /**
         * A Configuration carrying the choice's locale, so a caller can build
         * a `createConfigurationContext` overlay and read its resources.
         */
        fun configuration(locale: AppLocale): Configuration = Configuration().apply {
            setLocale(localeFor(locale))
        }
    }
}

/**
 * The Android-standard way Jetlink localizes: all user-visible text lives in
 * `res/values/strings.xml` (English) and `res/values-zh-rCN/strings.xml`
 * (Chinese), resolved by [Context]'s resources. `Context.graph`
 * (AppGraph) holds the current choice; see [AppLocale] for the manual
 * override and how `MainActivity` overlays it.
 *
 * The one helper here avoids repeating the locale plumbing at every call site.
 */
object L10n {

    /** The saved choice, or System when unset. */
    fun choice(context: Context): AppLocale =
        AppLocale.of(context.getSharedPreferences("settings", Context.MODE_PRIVATE)
            .getString("language", null)) ?: AppLocale.System

    /**
     * A Context whose resources are in `language`'s locale, for manual
     * overrides. Passed to anything that reads UI text via `stringResource`.
     * With [AppLocale.System] it is the plain context (no overlay), which is
     * exactly the stock behaviour.
     */
    fun overlay(context: Context, language: AppLocale): Context =
        if (language == AppLocale.System) context
        else context.createConfigurationContext(AppLocale.configuration(language))
}
