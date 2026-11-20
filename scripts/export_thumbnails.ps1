# Export every slide of a .pptx to PNG using installed Microsoft PowerPoint (Windows only).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/export_thumbnails.ps1 <deck.pptx> <out_dir>
param(
    [Parameter(Mandatory = $true)][string]$Deck,
    [Parameter(Mandatory = $true)][string]$OutDir
)
$deckPath = (Resolve-Path $Deck).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$outPath = (Resolve-Path $OutDir).Path

$app = New-Object -ComObject PowerPoint.Application
try {
    # Open(FileName, ReadOnly, Untitled, WithWindow)
    $pres = $app.Presentations.Open($deckPath, -1, 0, 0)
    $i = 1
    foreach ($slide in $pres.Slides) {
        $file = Join-Path $outPath ("slide_{0:D2}.png" -f $i)
        $slide.Export($file, "PNG", 1600, 900)
        $i++
    }
    $pres.Close()
    Write-Output "Exported $($i - 1) slides to $outPath"
}
finally {
    $app.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}
