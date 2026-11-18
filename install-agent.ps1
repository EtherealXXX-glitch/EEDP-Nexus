param([switch]$Wsl)
$ErrorActionPreference='Stop'
$appRoot=$PSScriptRoot
[Console]::OutputEncoding=New-Object Text.UTF8Encoding $false
$setupArgs=@('--plan')
$exe=Join-Path $appRoot 'EEDP-Agent.exe'
if(Test-Path -LiteralPath $exe){
    $planJson=& $exe setup @setupArgs
}else{
    $python=Join-Path $appRoot '.venv\Scripts\python.exe'
    if(!(Test-Path -LiteralPath $python)){
        if(Get-Command py -ErrorAction SilentlyContinue){& py -3 -m venv (Join-Path $appRoot '.venv')}
        elseif(Get-Command python -ErrorAction SilentlyContinue){& python -m venv (Join-Path $appRoot '.venv')}
        else{throw 'Install Python 3.12+ for Windows (including tkinter), or download the portable ZIP.'}
        if($LASTEXITCODE -ne 0){throw 'Python environment creation failed'}
    }
    & $python -m pip install -r (Join-Path $appRoot 'requirements.txt')
    if($LASTEXITCODE -ne 0){throw 'Dependency installation failed'}
    $env:PYTHONUTF8='1'
    $planJson=& $python (Join-Path $appRoot 'setup-agent.py') @setupArgs
}
if($LASTEXITCODE -ne 0){throw 'Agent registration failed'}
$plan=$planJson | ConvertFrom-Json
function Write-NexusFile($path,$text){
    $null=New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force
    if(Test-Path -LiteralPath $path){
        if([IO.File]::ReadAllText($path) -eq $text){return}
        Copy-Item -LiteralPath $path -Destination ($path+'.pre-nexus-'+[DateTime]::UtcNow.Ticks) -Force
    }
    [IO.File]::WriteAllText($path,$text,(New-Object Text.UTF8Encoding $false))
}
$existing=Get-Item -LiteralPath $plan.skill -Force -ErrorAction SilentlyContinue
if($existing -and ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)){
    Remove-Item -LiteralPath $plan.skill -Force
}
$null=New-Item -ItemType Directory -Path $plan.skill -Force
Copy-Item -Path (Join-Path $plan.skill_source '*') -Destination $plan.skill -Recurse -Force
Write-NexusFile $plan.config $plan.config_text
Write-NexusFile $plan.pointer $plan.pointer_text
Write-NexusFile $plan.generic_mcp $plan.generic_text
$shortcut=Join-Path ([Environment]::GetFolderPath('Desktop')) 'EEDP Nexus.lnk'
if(Test-Path -LiteralPath $shortcut){
    $shell=New-Object -ComObject WScript.Shell
    $link=$shell.CreateShortcut($shortcut)
    if($link.TargetPath -eq (Join-Path $appRoot 'EEDP Nexus.exe')){
        $link.IconLocation=(Join-Path $appRoot 'EEDP Nexus.exe')+',-1'
        $link.Save()
        if(Test-Path -LiteralPath $exe){& $exe shell $shortcut}
        else{& $python (Join-Path $appRoot 'windows_identity.py') $shortcut}
        if($LASTEXITCODE -ne 0){throw 'Shortcut identity registration failed'}
    }
}
if($Wsl){
    $linuxScript=(& wsl.exe -e wslpath -u (Join-Path $appRoot 'setup-agent.py')).Trim()
    if($LASTEXITCODE -ne 0){throw 'WSL path conversion failed'}
    & wsl.exe -e python3 $linuxScript
    if($LASTEXITCODE -ne 0){throw 'WSL registration failed'}
}
Write-Output 'EEDP Nexus Agent setup complete. Start a new Agent session. No hardware was accessed.'
