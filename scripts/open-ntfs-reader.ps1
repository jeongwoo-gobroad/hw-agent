param(
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$configPath = (Resolve-Path -LiteralPath $Config).Path
$settings = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$statePath = [string]$settings.state_directory
$windows = Get-Content -LiteralPath (Join-Path $statePath 'real-maintenance-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($windows.phase -ne 'inventory_and_decompression' -or $windows.safe_to_restore) {
    throw '임시 접근 단계가 종료되었습니다. 공유 복구 후 기존 SMB를 이용해 주세요.'
}
$readerScript = Join-Path $PSScriptRoot 'read-ntfs-files.py'
$listener = @(Get-NetTCPConnection -LocalPort $settings.port -State Listen -ErrorAction SilentlyContinue)
if ($listener.Count) {
    if ($listener.Count -ne 1 -or $listener[0].LocalAddress -ne '127.0.0.1') { throw '사용 중인 포트입니다.' }
    $existing = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener[0].OwningProcess)
    if (-not $existing.CommandLine -or -not $existing.CommandLine.Contains($readerScript) -or -not $existing.CommandLine.Contains($configPath)) {
        throw '다른 프로그램이 포트를 사용 중입니다.'
    }
} else {
    $arguments = @(('"{0}"' -f $readerScript), '--config', ('"{0}"' -f $configPath))
    $child = Start-Process -FilePath $Python -ArgumentList $arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $statePath 'reader.stdout.log') `
        -RedirectStandardError (Join-Path $statePath 'reader.stderr.log')
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        if ($child.HasExited) { throw '임시 파일 창을 시작하지 못했습니다.' }
        $listener = @(Get-NetTCPConnection -LocalPort $settings.port -State Listen -ErrorAction SilentlyContinue)
        if ($listener.Count -eq 1 -and $listener[0].OwningProcess -eq $child.Id -and $listener[0].LocalAddress -eq '127.0.0.1') { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $listener.Count -or $listener[0].OwningProcess -ne $child.Id) { throw '시작 응답을 확인하지 못했습니다.' }
}
$chrome = Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
if (-not (Test-Path -LiteralPath $chrome)) { $chrome = (Get-Command chrome.exe -ErrorAction Stop).Source }
$url = 'http://127.0.0.1:' + $settings.port + '/#token=' + [uri]::EscapeDataString($settings.token)
Start-Process -FilePath $chrome -ArgumentList $url -WindowStyle Normal
