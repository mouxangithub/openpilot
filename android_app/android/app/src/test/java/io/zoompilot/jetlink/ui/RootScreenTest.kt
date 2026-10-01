package io.zoompilot.jetlink.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** The launch extras benches and screenshots open the app with. */
class RootScreenTest {
    @Test
    fun tabs() {
        assertEquals(Tab.Models, initialTab("models", null))
        assertEquals(Tab.Benchmark, initialTab("benchmark", null))
        assertEquals(Tab.Settings, initialTab("logs", null))
        assertEquals(Tab.Settings, initialTab("connect", null))
        assertEquals(Tab.Status, initialTab(null, null))
        // a scripted benchmark opens on its tab unless another is asked for
        assertEquals(Tab.Benchmark, initialTab(null, 60))
        assertEquals(Tab.Status, initialTab("status", 60))
    }

    @Test
    fun pushedScreens() {
        assertEquals(Pushed.Logs, initialPushed("logs"))
        assertEquals(Pushed.Connect, initialPushed("connect"))
        assertNull(initialPushed("settings"))
        assertNull(initialPushed(null))
    }
}
