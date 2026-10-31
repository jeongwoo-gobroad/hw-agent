param(
    [Parameter(Mandatory=$true)][string]$StateDirectory,
    [Parameter(Mandatory=$true)][string]$DiskSerial,
    [string]$Python = 'python',
    [ValidateRange(2,60)][int]$IntervalSeconds = 5,
    [switch]$Once
)

$ErrorActionPreference = 'Stop'
$snapshotScript = Join-Path $PSScriptRoot 'ntfs_progress_snapshot.py'
$etaScript = Join-Path $PSScriptRoot 'ntfs_progress_eta.py'
$etaHistory = Join-Path $StateDirectory 'progress-eta-history.json'
$Host.UI.RawUI.WindowTitle = 'NTFS 압축 해제 진행 상황'
$diskIndex = $null
$lastDiscovery = [datetime]::MinValue
$lastWindowsPhase = $null
$lastSnapshot = $null
$phases = @{
    inventory='파일 목록 조사'; preflight_complete='여유 공간 검사 완료'
    decompressing='압축 해제 중'; complete='변환 완료'; complete_with_errors='변환 종료: 오류 있음'
    paused='일시 정지'; blocked_inventory_errors='목록 조사 오류'
    blocked_insufficient_space='공간 부족'; blocked_file_workspace='파일 변환 공간 부족'
    waiting_native_operation='Windows 파일 변환 대기'; preparing_resume='작업 재개 준비'
    waiting_resumed_operation='남은 파일 변환 중'; restoring_pi='Pi 공유 복구 중'
    restored_needs_verification='공유 복구됨: 최종 검증 대기'; needs_attention='확인 필요'
    inventory_and_decompression='Windows 변환 중'; queued='재개 대기'
    starting='연결 준비'; detaching='Windows 연결 해제 중'; finished='Windows 작업 종료'
    failed='실패'; unknown='상태 확인 중'
}

function Phase-Text($value) {
    if ($phases.ContainsKey([string]$value)) { return $phases[[string]$value] }
    return '상태 확인 중'
}
function Percent($done, $total) {
    if ($total -le 0) { return 0.0 }
    return [math]::Min(100.0, 100.0 * $done / $total)
}
function Size-Text($bytes) {
    if ($null -eq $bytes) { return '확인 중' }
    if ($bytes -ge 1TB) { return ('{0:N2} TiB' -f ($bytes / 1TB)) }
    if ($bytes -ge 1GB) { return ('{0:N2} GiB' -f ($bytes / 1GB)) }
    return ('{0:N2} MiB' -f ($bytes / 1MB))
}
function Duration-Text($seconds) {
    $minutes = [math]::Ceiling($seconds / 60)
    if ($minutes -lt 60) { return ('{0:N0}분' -f $minutes) }
    return ('{0:N0}시간 {1:N0}분' -f [math]::Floor($minutes / 60), ($minutes % 60))
}

try {
    do {
        $stale = $false
        try {
            $raw = & $Python $snapshotScript --state-directory $StateDirectory 2>$null
            if ($LASTEXITCODE -ne 0) { throw 'Snapshot unavailable' }
            $sample = $raw | ConvertFrom-Json
            $lastSnapshot = $sample
        } catch {
            $sample = $lastSnapshot
            $stale = $true
        }
        $io = $null
        try {
            $canReadCounters = $sample -and $sample.windows_phase -eq 'inventory_and_decompression'
            if ($sample.windows_phase -ne $lastWindowsPhase) { $diskIndex = $null }
            $lastWindowsPhase = $sample.windows_phase
            # 분리·복구 단계에서는 장치 조회를 멈춰 유지보수 작업과 경쟁하지 않는다.
            if ($canReadCounters -and $null -eq $diskIndex -and ((Get-Date) - $lastDiscovery).TotalSeconds -ge 30) {
                $matches = @(Get-CimInstance Win32_DiskDrive | Where-Object { $_.SerialNumber -and $_.SerialNumber.Trim() -eq $DiskSerial })
                $diskIndex = if ($matches.Count -eq 1) { $matches[0].Index } else { $null }
                $lastDiscovery = Get-Date
            }
            if ($canReadCounters -and $null -ne $diskIndex) {
                $io = Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Where-Object { ($_.Name -split ' ',2)[0] -eq [string]$diskIndex } | Select-Object -First 1
            }
        } catch { $io = $null }

        $eta = $null
        if ($sample -and -not $stale) {
            try {
                $etaArguments = @($etaScript, '--history', $etaHistory)
                if ($io -and ($io.DiskReadBytesPersec + $io.DiskWriteBytesPersec) -gt 0) {
                    $etaArguments += '--io-active'
                }
                $etaRaw = $sample | ConvertTo-Json -Depth 6 -Compress | & $Python @etaArguments 2>$null
                if ($LASTEXITCODE -eq 0) { $eta = $etaRaw | ConvertFrom-Json }
            } catch { $eta = $null }
        }

        $lines = [System.Collections.Generic.List[string]]::new()
        $lines.Add('NTFS 압축 해제 진행 상황')
        $lines.Add(('화면 갱신: {0:yyyy-MM-dd HH:mm:ss} | {1}초 간격' -f (Get-Date), $IntervalSeconds))
        $lines.Add('')
        if ($sample) {
            $lines.Add(('변환: {0} | 후속 처리: {1}' -f (Phase-Text $sample.worker_phase), (Phase-Text $sample.supervisor_phase)))
            if ($sample.inventory) {
                $files = $sample.inventory.stream
                $folders = $sample.inventory.directory
                $filePercent = Percent $files.done $files.total
                $bytePercent = Percent $files.done_bytes $files.logical_bytes
                $lines.Add(('파일 데이터: {0:N0} / {1:N0}건 완료 ({2:N3}%)' -f $files.done, $files.total, $filePercent))
                $lines.Add(('확정 완료 용량: {0} / {1} ({2:N3}%)' -f (Size-Text $files.done_bytes), (Size-Text $files.logical_bytes), $bytePercent))
                $lines.Add(('폴더 속성: {0:N0} / {1:N0}개 완료' -f $folders.done, $folders.total))
                $lines.Add(('남은 데이터: {0:N0}건 | 변환 오류: {1:N0}건 | 조사 오류: {2:N0}건' -f $files.pending, ($files.error + $folders.error), $sample.inventory_errors))
                $lines.Add(('남은 대기 용량: {0} | 오류 항목 용량: {1}' -f (Size-Text $files.pending_bytes), (Size-Text $files.error_bytes)))
            } else { $lines.Add('작업 DB 집계 대기 중') }
            if ($eta -and $eta.status -eq 'estimated') {
                $lines.Add(('최근 처리속도: {0:N1} MiB/s | 완료 기록 {1:N0}분 기준' -f ($eta.bytes_per_second / 1MB), ($eta.window_seconds / 60)))
                $lines.Add(('현재 변환 ETA: 약 {0} ~ {1}' -f (Duration-Text $eta.seconds_low), (Duration-Text $eta.seconds_high)))
                $lines.Add(('예상 종료 시각: {0:MM-dd HH:mm} ~ {1:MM-dd HH:mm} (PC 현지 시각)' -f (Get-Date).AddSeconds($eta.seconds_low), (Get-Date).AddSeconds($eta.seconds_high)))
            } elseif ($eta -and $eta.status -eq 'collecting') {
                $lines.Add('현재 변환 ETA: 완료 용량 표본 수집 중 (서로 다른 완료 기록과 1분 이상 구간 필요)')
            } else {
                $lines.Add('현재 변환 ETA: 대기 또는 복구 단계이거나 최신 속도 표본을 확인할 수 없습니다.')
            }
            $lines.Add(('마지막 파일 완료 기록: {0:N0}초 전' -f $sample.record_age_seconds))
            $lines.Add(('작업 관리자 응답: {0:N0}초 전' -f $sample.supervisor_age_seconds))
            $lines.Add(('마지막 기록의 여유 공간: {0}' -f (Size-Text $sample.free_bytes_at_last_record)))
            if ($sample.supervisor_age_seconds -gt 90 -and $sample.supervisor_phase -like 'waiting*') {
                $lines.Add('주의: 후속 처리 상태 갱신이 늦습니다. 창을 닫아도 변환은 계속됩니다.')
            }
        } else { $lines.Add('작업 상태 수집 대기 중') }
        $lines.Add('')
        if ($io) {
            $lines.Add(('디스크 읽기: {0:N1} MiB/s | 쓰기: {1:N1} MiB/s | 대기 I/O: {2}' -f ($io.DiskReadBytesPersec / 1MB), ($io.DiskWriteBytesPersec / 1MB), $io.CurrentDiskQueueLength))
        } else { $lines.Add('디스크 속도: 연결 해제 중이거나 성능 카운터를 확인할 수 없습니다.') }
        if ($stale) { $lines.Add('현재 상태를 읽지 못해 마지막 수집 결과를 표시합니다.') }
        $lines.Add('')
        $lines.Add('큰 파일은 처리 도중 완료 건수가 그대로일 수 있습니다.')
        $lines.Add('ETA는 최근 완료 속도가 유지된다는 가정입니다. 왼쪽 값만 현재 파일의 경과 시간을 추정 반영합니다.')
        $lines.Add('오른쪽 값은 대기 용량 전체 기준입니다. 범위는 보장 시간이 아니며 오류 재시도·공유 복구는 제외합니다.')
        $lines.Add('데이터 건수는 추가 데이터 스트림을 포함하며 실제 파일 수와 다를 수 있습니다.')
        $lines.Add('이 창은 조회 전용입니다. 창 닫기 / Ctrl+C는 압축 해제에 영향을 주지 않습니다.')
        if (-not $Once) { Clear-Host }
        Write-Host ($lines -join [Environment]::NewLine)
        if (-not $Once -and $sample.inventory) {
            Write-Progress -Id 1 -Activity '파일 데이터 압축 해제' -Status ('{0:N0} / {1:N0}건 완료' -f $files.done,$files.total) -PercentComplete $filePercent
        }
        if (-not $Once) { Start-Sleep -Seconds $IntervalSeconds }
    } while (-not $Once)
} finally {
    Write-Progress -Id 1 -Activity '파일 데이터 압축 해제' -Completed
}
