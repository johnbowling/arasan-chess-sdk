import groovy.json.JsonSlurper

plugins {
    id("com.android.library")
}

val repositoryDirectory = rootDir.resolve("../..").canonicalFile
val upstream = JsonSlurper().parse(repositoryDirectory.resolve("sdk/upstream.json")) as Map<*, *>
val network = upstream["network"] as Map<*, *>
val engineVersion = upstream["engineVersion"] as String
val networkSourcePath = network["sourcePath"] as String
val networkPackagedName = network["packagedName"] as String
val networkBytes = (network["bytes"] as Number).toLong()
val networkSha256 = network["sha256"] as String

fun androidProperty(name: String): String = providers.gradleProperty(name).get()
fun quoted(value: String): String = "\"${value.replace("\\", "\\\\").replace("\"", "\\\"")}\""

val generatedAssetsDirectory = layout.buildDirectory.dir("generated/arasanAssets")
val prepareArasanAssets by tasks.registering(Copy::class) {
    into(generatedAssetsDirectory)
    from(repositoryDirectory.resolve(networkSourcePath)) {
        into("arasan")
        rename { networkPackagedName }
    }
    from(repositoryDirectory.resolve("LICENSE")) {
        into("arasan")
        rename { "LICENSE" }
    }
    from(repositoryDirectory.resolve("doc/PROVENANCE.md")) {
        into("arasan")
        rename { "PROVENANCE.md" }
    }
}

android {
    namespace = "org.arasanchess.sdk"
    compileSdk = androidProperty("arasanCompileSdk").toInt()
    ndkVersion = androidProperty("arasanNdkVersion")

    defaultConfig {
        minSdk = androidProperty("arasanMinSdk").toInt()
        aarMetadata {
            minCompileSdk = androidProperty("arasanMinSdk").toInt()
        }
        ndk {
            abiFilters += androidProperty("arasanAbis").split(",")
        }
        externalNativeBuild {
            cmake {
                arguments += "-DANDROID_STL=c++_static"
            }
        }
        consumerProguardFiles("consumer-rules.pro")
        buildConfigField("String", "ENGINE_VERSION", quoted(engineVersion))
        buildConfigField("String", "NETWORK_ASSET", quoted(networkPackagedName))
        buildConfigField("long", "NETWORK_BYTES", "${networkBytes}L")
        buildConfigField("String", "NETWORK_SHA256", quoted(networkSha256))
    }

    externalNativeBuild {
        cmake {
            path = file("../CMakeLists.txt")
            version = androidProperty("arasanCmakeVersion")
        }
    }

    buildFeatures {
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    sourceSets.getByName("main").assets.srcDir(generatedAssetsDirectory.get().asFile)
    androidResources {
        noCompress += "nnue"
    }
}

tasks.named("preBuild").configure {
    dependsOn(prepareArasanAssets)
}
