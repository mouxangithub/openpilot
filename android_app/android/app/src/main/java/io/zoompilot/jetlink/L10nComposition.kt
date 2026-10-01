package io.zoompilot.jetlink

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.annotation.StringRes

/** The current manual language override, set at the top of MainActivity. */
val LocalAppLocale = staticCompositionLocalOf { AppLocale.System }

/**
 * A Context whose resources carry the override's locale, set alongside
 * [LocalAppLocale] in MainActivity. `System` is the plain activity context, so
 * this is a no-op unless the user picked English or 中文.
 */
val LocalOverlayContext = staticCompositionLocalOf<Context? > { null }

/**
 * Read a user-visible string honouring the manual language override. Drop-in
 * for `stringResource`: with `System` it is exactly the system-default string,
 * and with a manual choice it reads the same key from the overlay's locale.
 *
 * `res/values/strings.xml` is the English source of truth; the Chinese lives
 * in `res/values-zh-rCN/strings.xml`.
 */
@Composable
fun l10n(@StringRes resId: Int): String {
    val overlay = LocalOverlayContext.current
    return overlay?.getString(resId) ?: androidx.compose.ui.res.stringResource(resId)
}

/** Like [l10n], for strings with `%1$s`-style placeholders. */
@Composable
fun l10n(@StringRes resId: Int, vararg args: Any): String {
    val overlay = LocalOverlayContext.current
    return overlay?.getString(resId, *args) ?: androidx.compose.ui.res.stringResource(resId, *args)
}