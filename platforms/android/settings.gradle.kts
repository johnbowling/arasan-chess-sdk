pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
    plugins {
        val agpVersion = providers.gradleProperty("arasanAgpVersion").get()
        id("com.android.library") version agpVersion
        id("com.android.application") version agpVersion
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "arasan-chess-sdk-android"
include(":library", ":smoke")
