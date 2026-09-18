plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "org.djdancho.calendar"
    compileSdk = 34

    defaultConfig {
        applicationId = "org.djdancho.calendar"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
        ndk {
            // Реальные телефоны — ARM; x86_64 нужен только эмулятору и
            // втрое удлиняет сборку CPython.
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
    }

    // Ключ подписи берётся из окружения и в репозитории не лежит: файл кладёт
    // сборка на сервере из секретов. Если ключа нет — release собирается
    // неподписанным, и это честнее, чем подписать случайным отладочным:
    // обновление поверх такой версии поставить будет нельзя.
    val keystorePath = System.getenv("ANDROID_KEYSTORE_FILE")
    signingConfigs {
        if (keystorePath != null && file(keystorePath).exists()) {
            create("release") {
                storeFile = file(keystorePath)
                storeType = "PKCS12"
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfigs.findByName("release")?.let { signingConfig = it }
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

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.core:core-ktx:1.13.1")
    // Напоминания проверяются в фоне по расписанию системы: без WorkManager
    // пришлось бы держать собственный сервис, который система всё равно
    // прибьёт ради экономии батареи.
    implementation("androidx.work:work-runtime-ktx:2.9.1")
}

chaquopy {
    defaultConfig {
        version = "3.10"
    }
    sourceSets {
        getByName("main") {
            // Ядро календаря лежит вне модуля — в core/. Одна копия кода на
            // Android, Windows и тесты: правишь в одном месте, расходиться
            // нечему. Путь абсолютный — так он не зависит от того, из какого
            // каталога запущена сборка.
            srcDir(rootProject.file("../core").absolutePath)
        }
    }
}
