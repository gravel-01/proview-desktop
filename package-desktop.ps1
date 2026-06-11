param(
    [string]$CondaEnvName = 'lumin',
    [string[]]$WindowsTargets = @('nsis', 'portable'),
    [switch]$SkipFrontend,
    [switch]$SkipBackend,
    [switch]$SkipPackage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = 'utf-8'

$repoRoot = $PSScriptRoot
$desktopDir = Join-Path $repoRoot 'desktop'
$releaseDir = Join-Path $desktopDir 'release'
$sanitizedEnvPath = Join-Path $desktopDir 'build\.env'
$logDir = Join-Path $repoRoot 'logs\desktop-package'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logFile = Join-Path $logDir "desktop-package-$timestamp.log"
$script:CondaPrefix = ''
$script:PowerShellHost = 'powershell'

$allowedEnvKeys = @(
    'LOCAL_USER_NAME',
    'ANY_MODEL_ENDPOINT',
    'DEEPSEEK_BASE_URL',
    'ERNIE_BASE_URL',
    'LOCAL_EMBEDDING_MODEL_DIR',
    'LOCAL_EMBEDDING_MAX_LENGTH',
    'EMBEDDING_BASE_URL',
    'EMBEDDING_MODEL',
    'EMBEDDING_DIMENSIONS',
    'EMBEDDING_BATCH_SIZE'
)

$script:LogWriter = $null

function Initialize-LogWriter {
    try {
        $stream = [System.IO.FileStream]::new(
            $logFile,
            [System.IO.FileMode]::Append,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::ReadWrite
        )
        $script:LogWriter = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        $script:LogWriter.AutoFlush = $true
    } catch {
        $script:LogWriter = $null
        Write-Host "[WARN] Unable to open log file for append: $($_.Exception.Message)"
    }
}

function Close-LogWriter {
    if ($null -ne $script:LogWriter) {
        try {
            $script:LogWriter.Dispose()
        } catch {
        } finally {
            $script:LogWriter = $null
        }
    }
}

function Write-Log {
    param(
        [string]$Message
    )

    $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message
    Write-Host $line
    if ($null -ne $script:LogWriter) {
        try {
            $script:LogWriter.WriteLine($line)
        } catch {
            Write-Host "[WARN] Failed to write log entry: $($_.Exception.Message)"
        }
    }
}

function Write-LogLine {
    param(
        [AllowEmptyString()]
        [string]$Line
    )

    if ($null -ne $script:LogWriter) {
        try {
            $script:LogWriter.WriteLine($Line)
            return
        } catch {
            Write-Host "[WARN] Failed to write captured output: $($_.Exception.Message)"
        }
    }

    [System.IO.File]::AppendAllText($logFile, $Line + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}

function Write-Section {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title
    )

    Write-Log ''
    Write-Log ('=' * 72)
    Write-Log $Title
    Write-Log ('=' * 72)
}

function Format-ArgumentList {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    return ($Arguments | ForEach-Object {
        if ($_ -match '\s') {
            '"{0}"' -f $_
        } else {
            $_
        }
    }) -join ' '
}

function Assert-PathExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Description not found: $Path"
    }
}

function Invoke-LoggedNativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    Write-Log "执行: $Description"
    Write-Log ("命令: {0} {1}" -f $FilePath, (Format-ArgumentList -Arguments $Arguments))

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    try {
        $process = Start-Process `
            -FilePath $FilePath `
            -ArgumentList (Format-ArgumentList -Arguments $Arguments) `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        foreach ($capturedPath in @($stdoutPath, $stderrPath)) {
            if (-not (Test-Path -LiteralPath $capturedPath)) {
                continue
            }

            foreach ($line in Get-Content -LiteralPath $capturedPath) {
                Write-Host $line
                Write-LogLine -Line $line
            }
        }

        $exitCode = $process.ExitCode
        if ($exitCode -ne 0) {
            throw "命令执行失败: $Description (exit code $exitCode)"
        }
    } finally {
        foreach ($capturedPath in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $capturedPath) {
                Remove-Item -LiteralPath $capturedPath -Force
            }
        }
    }
}

function Invoke-LoggedPowerShellScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$ScriptArguments = @(),
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    Assert-PathExists -Path $ScriptPath -Description $Description
    $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath) + $ScriptArguments
    Invoke-LoggedNativeCommand -FilePath $script:PowerShellHost -Arguments $args -Description $Description
}

function Get-CondaEnvironmentPrefix {
    $condaCommand = Get-Command conda -ErrorAction Stop
    $rawOutput = & $condaCommand.Source 'env' 'list' '--json' 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Unable to read the Conda environment list (exit code $exitCode)"
    }

    $jsonText = ($rawOutput | ForEach-Object { "$_" }) -join [Environment]::NewLine
    $envInfo = $jsonText | ConvertFrom-Json
    $matched = $envInfo.envs | Where-Object { (Split-Path $_ -Leaf) -eq $CondaEnvName } | Select-Object -First 1
    if (-not $matched) {
        throw "Conda environment not found: $CondaEnvName"
    }

    return [string]$matched
}

function Enable-CondaEnvironmentForCurrentProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prefix
    )

    $pathEntries = @(
        $Prefix,
        (Join-Path $Prefix 'Scripts'),
        (Join-Path $Prefix 'Library\bin'),
        (Join-Path $Prefix 'Library\usr\bin'),
        (Join-Path $Prefix 'DLLs')
    )

    $merged = New-Object System.Collections.Generic.List[string]
    $seen = @{}

    foreach ($entry in $pathEntries + ($env:Path -split ';')) {
        $text = [string]$entry
        if ([string]::IsNullOrWhiteSpace($text)) {
            continue
        }

        $normalized = $text.Trim()
        if ($seen.ContainsKey($normalized.ToLowerInvariant())) {
            continue
        }

        $seen[$normalized.ToLowerInvariant()] = $true
        $merged.Add($normalized)
    }

    $env:Path = $merged -join ';'
    $env:CONDA_DEFAULT_ENV = $CondaEnvName
    $env:CONDA_PREFIX = $Prefix
    $env:CONDA_PROMPT_MODIFIER = "($CondaEnvName) "
}

function Format-Duration {
    param(
        [Parameter(Mandatory = $true)]
        [TimeSpan]$Duration
    )

    return "{0:D2}:{1:D2}:{2:D2}" -f [int]$Duration.TotalHours, $Duration.Minutes, $Duration.Seconds
}

function Get-StepDefinitions {
    $steps = @(
        @{
            Name = 'Environment check'
            Action = {
                Assert-PathExists -Path $desktopDir -Description 'desktop directory'
                Assert-PathExists -Path (Join-Path $desktopDir 'scripts\build-frontend.ps1') -Description 'frontend build script'
                Assert-PathExists -Path (Join-Path $desktopDir 'scripts\build-backend.ps1') -Description 'backend build script'
                Assert-PathExists -Path (Join-Path $desktopDir 'scripts\package-app.ps1') -Description 'desktop packaging script'

                $null = Get-Command conda -ErrorAction Stop
                $null = Get-Command node -ErrorAction Stop
                $null = Get-Command npm -ErrorAction Stop
                $pwshCommand = Get-Command pwsh -ErrorAction SilentlyContinue
                if ($pwshCommand) {
                    $script:PowerShellHost = $pwshCommand.Source
                } else {
                    $script:PowerShellHost = (Get-Command powershell -ErrorAction Stop).Source
                }

                $script:CondaPrefix = ''
                try {
                    $script:CondaPrefix = Get-CondaEnvironmentPrefix
                    Enable-CondaEnvironmentForCurrentProcess -Prefix $script:CondaPrefix
                } catch {
                    Write-Log "Warning: $($_.Exception.Message)"
                    Write-Log 'Falling back to the current Python environment.'
                }

                $nodeVersion = (& node -v).Trim()
                if ($LASTEXITCODE -ne 0) {
                    throw 'Unable to get Node.js version.'
                }

                $npmVersion = (& npm -v).Trim()
                if ($LASTEXITCODE -ne 0) {
                    throw 'Unable to get npm version.'
                }

                Write-Log "Repo root: $repoRoot"
                Write-Log "Desktop dir: $desktopDir"
                Write-Log "Release dir: $releaseDir"
                Write-Log "Log file: $logFile"
                Write-Log "Conda env: $CondaEnvName"
                Write-Log "Conda prefix: $script:CondaPrefix"
                Write-Log "PowerShell host: $script:PowerShellHost"
                Write-Log "Windows packaging targets: $($WindowsTargets -join ', ')"
                Write-Log "Node.js version: $nodeVersion"
                Write-Log "npm version: $npmVersion"

                Invoke-LoggedNativeCommand `
                    -FilePath 'python' `
                    -Arguments @(
                        '-c',
                        'import sys; print(sys.executable); print(sys.version.split()[0])'
                    ) `
                    -Description 'Check Python in the Conda environment'
            }
        }
    )

    if (-not $SkipFrontend) {
        $steps += @{
            Name = 'Build frontend'
            Action = {
                Invoke-LoggedPowerShellScript `
                    -ScriptPath (Join-Path $desktopDir 'scripts\build-frontend.ps1') `
                    -Description 'Build desktop frontend assets'
            }
        }
    }

    if (-not $SkipBackend) {
        $steps += @{
            Name = 'Build backend'
            Action = {
                Invoke-LoggedPowerShellScript `
                    -ScriptPath (Join-Path $desktopDir 'scripts\build-backend.ps1') `
                    -Description 'Build distributable backend assets'

                Assert-PathExists -Path $sanitizedEnvPath -Description 'sanitized .env'
                $sanitizedKeys = @()
                foreach ($line in Get-Content -LiteralPath $sanitizedEnvPath) {
                    if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) {
                        continue
                    }

                    $separatorIndex = $line.IndexOf('=')
                    if ($separatorIndex -lt 1) {
                        continue
                    }

                    $key = $line.Substring(0, $separatorIndex).Trim()
                    $sanitizedKeys += $key
                    if ($allowedEnvKeys -notcontains $key) {
                        throw "Sanitized .env contains an unsupported key: $key"
                    }
                }

                Write-Log "Sanitized .env generated: $sanitizedEnvPath"
                if ($sanitizedKeys.Count -gt 0) {
                    Write-Log "Retained bootstrap keys: $($sanitizedKeys -join ', ')"
                } else {
                    Write-Log 'Sanitized .env is empty; only script defaults will be used.'
                }
            }
        }
    }

    if (-not $SkipPackage) {
        $steps += @{
            Name = 'Package desktop app'
            Action = {
                Invoke-LoggedPowerShellScript `
                    -ScriptPath (Join-Path $desktopDir 'scripts\package-app.ps1') `
                    -ScriptArguments (@('--win') + $WindowsTargets) `
                    -Description 'Generate installer, portable build, and unpacked output'
            }
        }
    }

    $steps += @{
        Name = 'Verify artifacts'
        Action = {
            Assert-PathExists -Path $releaseDir -Description 'release output directory'

            $entries = Get-ChildItem -LiteralPath $releaseDir -Force | Sort-Object Name
            if (-not $entries) {
                throw "No artifacts were found in $releaseDir."
            }

            $topLevelEntries = $entries | ForEach-Object {
                if ($_.PSIsContainer) {
                    "[dir] $($_.Name)"
                } else {
                    "{0} ({1:N2} MB)" -f $_.Name, ($_.Length / 1MB)
                }
            }

            Write-Log 'Release directory artifacts:'
            foreach ($entry in $topLevelEntries) {
                Write-Log "  - $entry"
            }

            $winUnpackedExe = Join-Path $releaseDir 'win-unpacked\ProView AI Interviewer.exe'
            if (Test-Path -LiteralPath $winUnpackedExe) {
                Write-Log "Unpacked executable: $winUnpackedExe"
            } else {
                Write-Log 'win-unpacked executable was not found; please check electron-builder output.'
            }
        }
    }

    return $steps
}

$steps = Get-StepDefinitions
$totalSteps = $steps.Count
$overallStart = Get-Date

Initialize-LogWriter

try {
    Write-Section 'ProView Desktop packaging started'
    Write-Log 'Note: backend packaging automatically generates a sanitized .env, so sensitive secrets are excluded from the desktop build.'

    for ($index = 0; $index -lt $totalSteps; $index++) {
        $step = $steps[$index]
        $stepNumber = $index + 1
        $startPercent = [int](($index / $totalSteps) * 100)
        $endPercent = [int](($stepNumber / $totalSteps) * 100)

        Write-Progress `
            -Activity 'ProView Desktop packaging progress' `
            -Status ("Step {0}/{1}: {2}" -f $stepNumber, $totalSteps, $step.Name) `
            -PercentComplete $startPercent

        Write-Section ("Step {0}/{1}: {2}" -f $stepNumber, $totalSteps, $step.Name)
        $stepStart = Get-Date
        & $step.Action
        $duration = (Get-Date) - $stepStart

        Write-Log ("Step completed: {0}, elapsed {1}" -f $step.Name, (Format-Duration -Duration $duration))
        Write-Progress `
            -Activity 'ProView Desktop packaging progress' `
            -Status ("Step {0}/{1}: {2} completed" -f $stepNumber, $totalSteps, $step.Name) `
            -PercentComplete $endPercent
    }

    $totalDuration = (Get-Date) - $overallStart
    Write-Progress -Activity 'ProView Desktop packaging progress' -Completed
    Write-Section 'Packaging completed'
    Write-Log ("Total elapsed: {0}" -f (Format-Duration -Duration $totalDuration))
    Write-Log "Detailed log: $logFile"
    Write-Log "Desktop artifact directory: $releaseDir"
} finally {
    Close-LogWriter
}
