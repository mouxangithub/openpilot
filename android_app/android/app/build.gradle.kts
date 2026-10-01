import java.io.File
import javax.inject.Inject

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

/** jetlink's version, from the Python package as the Mac and iPhone apps read it. */
val jetlinkVersion: String =
    Regex("""__version__ = '([^']+)'""")
        .find(rootDir.resolve("../../jetlink_repo/jetlink/__init__.py").readText())
        ?.groupValues?.get(1) ?: "0.0.0"

/** 0.5.0 is 500: releases only go up. */
val jetlinkVersionCode: Int =
    jetlinkVersion.split(".").map { it.takeWhile(Char::isDigit).toIntOrNull() ?: 0 }
        .let { (it.getOrElse(0) { 0 } * 10000) + (it.getOrElse(1) { 0 } * 100) + it.getOrElse(2) { 0 } }

android {
    namespace = "io.zoompilot.jetlink"
    compileSdk = 37
    // The NDK the Swift SDK for Android was built with; AGP strips the
    // native libraries with it.
    ndkVersion = "30.0.16248370"

    defaultConfig {
        applicationId = "io.zoompilot.jetlink.android"
        // Android 12: Build.SOC_MODEL and the performance hint API.
        minSdk = 31
        targetSdk = 36
        versionCode = jetlinkVersionCode
        versionName = jetlinkVersion
        // The QNN runtime is arm64 only, and so is every Snapdragon with an NPU
        // worth driving on. The emulator on an Apple silicon Mac is arm64 too.
        ndk { abiFilters += "arm64-v8a" }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // Sideloaded, never on a store: the debug key, so a release build
            // installs over a debug one. Replace it to publish.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        jniLibs {
            // The NPU's skel libraries are loaded by the DSP from a real file,
            // so native libraries are extracted to nativeLibraryDir.
            useLegacyPackaging = true
            // onnxruntime's Java binding; the server calls the C API.
            excludes += "**/libonnxruntime4j_jni.so"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

/** The onnxruntime AAR on its own, for its C headers. */
val onnxruntimeAar: Configuration by configurations.creating {
    isCanBeConsumed = false
    isTransitive = false
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.service)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.kotlinx.serialization.json)
    // libonnxruntime.so with the QNN provider, and the QNN runtime's libraries
    implementation(libs.onnxruntime.qnn)
    debugImplementation(libs.compose.ui.tooling)

    onnxruntimeAar(variantOf(libs.onnxruntime.qnn) { artifactType("aar") })

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}

/**
 * Builds libjetlink.so, the server, with the Swift SDK for Android
 * (scripts/swift-build.sh). Always optimized: the frame path in an
 * unoptimized build is too slow to judge anything by.
 *
 * -Pjetlink.prebuiltSwift=DIR skips the Swift build and packages DIR/arm64-v8a
 * instead, for working on the Kotlin side without the Swift toolchain.
 */
abstract class SwiftBuild @Inject constructor(private val exec: ExecOperations) : DefaultTask() {
    @get:OutputDirectory abstract val outputDir: DirectoryProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val sources: ConfigurableFileCollection
    @get:InputFiles @get:PathSensitive(PathSensitivity.NONE) abstract val onnxruntime: ConfigurableFileCollection
    @get:Internal abstract val script: RegularFileProperty
    @get:Input @get:Optional abstract val prebuilt: Property<String>
    /** The prebuilt libraries' contents, so a new copy there is picked up. */
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val prebuiltFiles: ConfigurableFileCollection

    @TaskAction
    fun build() {
        val out = outputDir.get().asFile
        val prebuiltDir = prebuilt.orNull
        if (prebuiltDir != null) {
            File(prebuiltDir).copyRecursively(out, overwrite = true)
            return
        }
        exec.exec {
            commandLine("bash", script.get().asFile.absolutePath, out.absolutePath, onnxruntime.singleFile.absolutePath, "release")
        }
    }
}

val swiftBuild = tasks.register<SwiftBuild>("swiftBuild") {
    val kit = rootDir.resolve("../JetlinkKit")
    sources.from(kit.resolve("Package.swift"), fileTree(kit.resolve("Sources")))
    onnxruntime.from(onnxruntimeAar)
    script.set(rootDir.resolve("scripts/swift-build.sh"))
    prebuilt.set(providers.gradleProperty("jetlink.prebuiltSwift"))
    providers.gradleProperty("jetlink.prebuiltSwift").orNull?.let { prebuiltFiles.from(fileTree(it)) }
    outputDir.set(layout.buildDirectory.dir("swift/jniLibs"))
}

androidComponents {
    onVariants { variant ->
        variant.sources.jniLibs?.addGeneratedSourceDirectory(swiftBuild, SwiftBuild::outputDir)
    }
}
