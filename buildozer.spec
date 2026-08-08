[app]
title = 桌宠爱心版
package.name = petheart
package.domain = com.example
source.dir = android_app
source.include_exts = py,png,jpg,kv,atlas,wav,ttf,txt
version = 1.0.0
requirements = python3,kivy==2.3.1,numpy==1.26.4,pillow==10.4.0,plyer,pyjnius
orientation = portrait
fullscreen = 0
android.permissions = INTERNET, RECORD_AUDIO, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, TTS
android.api = 35
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.entrypoint = main.py
presplash.filename = data/splash.png

[buildozer]
log_level = 2
warn_on_root = 1