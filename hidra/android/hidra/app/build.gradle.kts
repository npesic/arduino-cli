plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.hidra"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.hidra"
        minSdk = 28          // BluetoothHidDevice arrives in API 28; Pixel 2 XL runs API 30
        targetSdk = 35
        versionCode = 1
        versionName = "0.2-phase1"
    }

    buildTypes {
        getByName("debug") { isMinifyEnabled = false }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions { jvmTarget = "17" }
}

// ReportBuilder is deliberately plain Kotlin so it can be tested on the JVM. JUnit is the only
// dependency in the project, and it never ships in the APK.
dependencies {
    testImplementation("junit:junit:4.13.2")
}

// The keyboard page is not forked. index.html / style.css / keymap.js / app.js are copied out of
// src/web/ at build time — the same files the ESP32 firmware serves — so a fix to the layout
// lands in both builds. Only transport.js is Android's own, and it lives in src/main/assets/
// where it shadows the WebSocket one by simply not being copied over.
val keyboardAssets = layout.buildDirectory.dir("generated/keyboard")

val syncKeyboard by tasks.registering(Copy::class) {
    from(rootProject.file("../../src/web")) {
        include("index.html", "style.css", "keymap.js", "app.js")
    }
    into(keyboardAssets)
}

android.sourceSets["main"].assets.srcDir(keyboardAssets)

tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }
    .configureEach { dependsOn(syncKeyboard) }
