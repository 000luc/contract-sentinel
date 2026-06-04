' Contract Sentinel - 后台静默启动（无窗口）
' 每5分钟检查一次OA，有新合同自动下载
' 要停止：打开任务管理器，结束 python.exe 进程

Dim shell
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "D:\BaiduSyncdisk\claude\contract-sentinel"
shell.Run "cmd /c set PYTHONPATH=src && py src\run_contract_polling.py", 0, False
Set shell = Nothing
