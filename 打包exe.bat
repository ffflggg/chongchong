@echo off
chcp 65001 >nul
echo ============================================
echo  桌宠爱心版 - 打包为单文件 exe（无控制台窗口）
echo  启动后屏幕右下角出现爱心，点击打开操作面板
echo  内嵌 u2netp 抠图模型，对方无需联网、无需装 Python
echo ============================================
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
if errorlevel 1 goto :fail
pyinstaller -F -w --name 桌宠爱心版 --add-data "config.json;." --add-data "models;models" --hidden-import rembg --hidden-import onnxruntime main.py
if errorlevel 1 goto :fail
echo.
echo 打包完成！把 dist\桌宠爱心版.exe 发给朋友：
echo   - 双击启动 → 屏幕出现【爱心】悬浮球
echo   - 点击爱心 = 打开操作面板；再点 = 隐藏
echo   - 设置完图片后桌宠直接上桌
echo   - 右键/长按桌宠可设置待办提醒、换动作等
echo   - 爱心可按住拖动到喜欢的位置
pause
exit /b 0
:fail
echo 打包失败，请检查网络后重试
pause
exit /b 1