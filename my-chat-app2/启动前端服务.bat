@echo off
chcp 65001 >nul
echo ========================================
echo LoRA 聊天系统 - 前端静态服务器
echo ========================================
echo.
cd /d D:\Task_design\my-chat-app2

REM 检查 dist 文件夹是否存在
if not exist "dist" (
    echo [错误] dist 文件夹不存在！
    echo 请先运行: npm run build
    echo.
    pause
    exit /b 1
)

echo 正在启动静态文件服务器（端口 5173）...
echo.
echo 访问地址：
echo   - 本机: http://localhost:5173
echo   - 局域网: http://[你的IP地址]:5173
echo.
echo 提示: 使用 ipconfig 查看你的IP地址
echo.

npx serve dist -l 5173 --cors
pause
