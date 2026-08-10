plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.hidra.spike"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.hidra.spike"
        minSdk = 28          // BluetoothHidDevice arrives in API 28 (Android 9)
        targetSdk = 35
        versionCode = 1
        versionName = "0.1-phase0"
    }

    buildTypes {
        // Debug-only spike: `assembleDebug` produces a sideloadable APK signed with the
        // auto-generated debug key. No release config until there is something to release.
        getByName("debug") {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

// No dependencies on purpose. The UI is framework views, the permission handling is
// Activity.requestPermissions, and the Bluetooth API is platform. Nothing here needs AndroidX,
// which keeps the build small and the failure surface tiny while we are testing one hypothesis.
dependencies { }
