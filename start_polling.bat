@echo off
chcp 65001 >nul
cd /d "D:\BaiduSyncdisk\claude\contract-sentinel"
set PYTHONPATH=src
echo Contract Sentinel - 合同审批轮询
echo ================================
echo 每5分钟检查一次OA
echo 关闭此窗口即停止
echo.
py src\run_contract_polling.py
if errorlevel 1 (
    echo.
    echo 运行出错，请检查 Cookie 是否有效
    pause
)
