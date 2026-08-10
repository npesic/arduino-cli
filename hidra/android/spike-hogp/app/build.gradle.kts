plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.hidra.hogp"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.hidra.hogp"   // distinct id: installs alongside the phase 0 spike
        minSdk = 28
        targetSdk = 35
        versionCode = 1
        versionName = "0.1-phase0b"
    }

    buildTypes { getByName("debug") { isMinifyEnabled = false } }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions { jvmTarget = "17" }
}

dependencies { }
