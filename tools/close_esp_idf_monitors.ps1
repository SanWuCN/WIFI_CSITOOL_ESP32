$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        ($_.CommandLine -match "idf_monitor.py" -or $_.CommandLine -match "esp_idf_monitor")
    }

if (-not $processes) {
    Write-Host "没有发现 ESP-IDF Monitor 进程。"
    exit 0
}

$processes | ForEach-Object {
    Write-Host "结束进程 $($_.ProcessId): $($_.CommandLine)"
    Stop-Process -Id $_.ProcessId -Force
}

Write-Host "已结束 ESP-IDF Monitor 进程。"
