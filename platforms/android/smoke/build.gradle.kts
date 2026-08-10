plugins {
    id("com.android.application")
}

fun androidProperty(name: String): String = providers.gradleProperty(name).get()

android {
    namespace = "org.arasanchess.sdk.smoke"
    compileSdk = androidProperty("arasanCompileSdk").toInt()
    ndkVersion = androidProperty("arasanNdkVersion")

    defaultConfig {
        applicationId = "org.arasanchess.sdk.smoke"
        minSdk = androidProperty("arasanMinSdk").toInt()
        targetSdk = androidProperty("arasanTargetSdk").toInt()
        versionCode = 1
        versionName = "1.0"
        ndk {
            abiFilters += listOf("x86_64")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation(project(":library"))
}
