$ErrorActionPreference = "Stop"

function Get-GitCredentialValue {
    param([string]$HostName)
    $inputText = "protocol=https`nhost=$HostName`n`n"
    $raw = $inputText | git credential fill
    $result = @{}
    foreach ($line in $raw) {
        $idx = $line.IndexOf("=")
        if ($idx -gt 0) {
            $result[$line.Substring(0, $idx)] = $line.Substring($idx + 1)
        }
    }
    return $result
}

$setupHash = "DC7292DFB32F41E3349A253079A8AF710D427D0ACED81DD7418725123BD06ECC"
$portableHash = "90DBFACFC2B95D697B3EE37D4F25CCC98ED4937B2200E4BEB9F9375C72173893"
$title = "SwCSI V1.0.1 installer release"

$commonLines = @(
    "SwCSI V1.0.1 is now available.",
    "",
    "SHA256:",
    "- SwCSI_V1.0.1_Setup.exe: $setupHash",
    "- SwCSI_V1.0.1_Portable.zip: $portableHash",
    "",
    "Highlights:",
    "- Renamed the desktop application to SwCSI.",
    "- Added the SwCSI application icon.",
    "- Added top menu, Settings panel, and UI language selection.",
    "- Added project save/load support with .swcsi files.",
    "- Added Doppler/STFT visualization.",
    "",
    "Contact: 1292053575@qq.com"
)

$githubLines = $commonLines + @(
    "",
    "Downloads:",
    "- Windows installer: https://github.com/SanWuCN/WIFI_CSITOOL_ESP32/raw/main/release_assets/v1.0.1/SwCSI_V1.0.1_Setup.exe",
    "- Portable package: https://github.com/SanWuCN/WIFI_CSITOOL_ESP32/raw/main/release_assets/v1.0.1/SwCSI_V1.0.1_Portable.zip"
)
$giteeLines = $commonLines + @(
    "",
    "Downloads:",
    "- Windows installer: https://gitee.com/swartcore/wifi_-csitool_-esp32/raw/master/release_assets/v1.0.1/SwCSI_V1.0.1_Setup.exe",
    "- Portable package: https://gitee.com/swartcore/wifi_-csitool_-esp32/raw/master/release_assets/v1.0.1/SwCSI_V1.0.1_Portable.zip"
)

$githubBody = $githubLines -join "`n"
$giteeBody = $giteeLines -join "`n"

try {
    $cred = Get-GitCredentialValue -HostName "github.com"
    if (-not $cred.password) {
        throw "No GitHub credential found."
    }
    $pair = "{0}:{1}" -f $cred.username, $cred.password
    $basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
    $payload = @{ title = $title; body = $githubBody } | ConvertTo-Json -Depth 4
    $res = Invoke-RestMethod `
        -Method Post `
        -Uri "https://api.github.com/repos/SanWuCN/WIFI_CSITOOL_ESP32/issues" `
        -Headers @{
            Authorization = "Basic $basic"
            "User-Agent" = "SwCSI-release-script"
            Accept = "application/vnd.github+json"
        } `
        -Body $payload `
        -ContentType "application/json"
    Write-Output "github_issue=$($res.html_url)"
} catch {
    Write-Output "github_issue_failed=$($_.Exception.Message)"
}

try {
    $cred = Get-GitCredentialValue -HostName "gitee.com"
    if (-not $cred.password) {
        throw "No Gitee credential found."
    }
    $res = Invoke-RestMethod `
        -Method Post `
        -Uri "https://gitee.com/api/v5/repos/swartcore/wifi_-csitool_-esp32/issues" `
        -Body @{
            access_token = $cred.password
            title = $title
            body = $giteeBody
        }
    Write-Output "gitee_issue=$($res.html_url)"
} catch {
    Write-Output "gitee_issue_failed=$($_.Exception.Message)"
}
