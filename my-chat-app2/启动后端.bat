@echo off
chcp 65001 >nul
echo ========================================
echo LoRA 聊天系统 - 后端服务器
echo ========================================
echo.
cd /d D:\Task_design
echo 正在启动后端服务器（端口 8765）...
echo.
python backend/Websocket.py
pause
