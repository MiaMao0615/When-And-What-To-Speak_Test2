@echo off
chcp 65001 >nul
echo ========================================
echo LoRA 聊天系统 - 构建前端
echo ========================================
echo.
cd /d D:\Task_design\my-chat-app2

echo 正在构建前端静态文件...
echo.

npm run build

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [成功] 构建完成！
    echo 文件已生成到 dist/ 文件夹
    echo.
    echo 接下来可以：
    echo   1. 双击 "启动前端服务.bat" 启动静态服务器
    echo   2. 或在终端运行: npx serve dist -l 5173 --cors
    echo.
) else (
    echo.
    echo [错误] 构建失败！
    echo.
)

pause
