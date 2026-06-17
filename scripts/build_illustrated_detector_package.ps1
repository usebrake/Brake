param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputPath) {
    $OutputPath = Join-Path $repoRoot "dist\BrakeIllustratedDetector.zip"
}

$tempData = Join-Path ([IO.Path]::GetTempPath()) ("brake-illustrated-export-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempData | Out-Null

try {
    $env:BRAKE_DATA_DIR = $tempData
    $env:BRAKE_ILLUSTRATED_DETECTOR_URL = "off"
    python -c "from brake.detectors.anime_nsfw import download_model; download_model()"
    if ($LASTEXITCODE -ne 0) { throw "illustrated detector export failed with $LASTEXITCODE" }

    $modelDir = Join-Path $tempData "models\anime_nsfw_falconsai"
    $required = @("config.json", "preprocessor_config.json", "model.int8.onnx")
    foreach ($name in $required) {
        $path = Join-Path $modelDir $name
        if (-not (Test-Path $path)) {
            throw "Missing exported detector file: $path"
        }
    }

    $manifest = @{
        name = "Brake illustrated detector"
        source = "Falconsai/nsfw_image_detection"
        revision = "04367978d3474804ab1a00a9bd6548b741764069"
        format = "onnx-int8"
    } | ConvertTo-Json
    Set-Content -Encoding UTF8 -Path (Join-Path $modelDir "manifest.json") -Value $manifest

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null
    if (Test-Path $OutputPath) { Remove-Item -LiteralPath $OutputPath -Force }
    Compress-Archive -Path (Join-Path $modelDir "config.json"), (Join-Path $modelDir "preprocessor_config.json"), (Join-Path $modelDir "model.int8.onnx"), (Join-Path $modelDir "manifest.json") -DestinationPath $OutputPath
    Write-Host "Illustrated detector package complete: $OutputPath"
} finally {
    Remove-Item -LiteralPath $tempData -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\BRAKE_DATA_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:\BRAKE_ILLUSTRATED_DETECTOR_URL -ErrorAction SilentlyContinue
}
