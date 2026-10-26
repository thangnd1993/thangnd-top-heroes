# Persistent Windows.Media.Ocr reader: one image path per stdin line, one JSON line per reply.
# Same engine, language and output shape as read-image-text.ps1; avoids starting PowerShell
# and loading WinRT for every counter/label read. An empty line or EOF ends the process.
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
$asyncMethod=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {$_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'} | Select-Object -First 1
function Await-Result($operation,[Type]$resultType) {
    $task=$asyncMethod.MakeGenericMethod($resultType).Invoke($null,@($operation))
    try {if (!$task.Wait(10000)) {throw 'OCR operation timeout'}} catch {throw $task.Exception.GetBaseException()}
    return $task.Result
}
$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US'))
while ($true) {
    $path=[Console]::In.ReadLine()
    if ([string]::IsNullOrEmpty($path)) { break }
    try {
        if (!$engine) {throw 'English Windows OCR is unavailable; no guessed counter'}
        $file=Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync([IO.Path]::GetFullPath($path))) ([Windows.Storage.StorageFile])
        $stream=Await-Result ($file.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
        try {
            $decoder=Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap=Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            $result=Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $words=@(foreach($line in $result.Lines) {foreach($word in $line.Words) {
                [pscustomobject]@{text=$word.Text;x=$word.BoundingRect.X;y=$word.BoundingRect.Y;width=$word.BoundingRect.Width;height=$word.BoundingRect.Height}
            }})
            $reply=[pscustomobject]@{engine='Windows.Media.Ocr';language=$engine.RecognizerLanguage.LanguageTag;text=$result.Text;words=$words}
            $bitmap.Dispose()
        } finally {$stream.Dispose()}
    } catch {
        $reply=[pscustomobject]@{engine='error';error=$_.Exception.Message;words=@()}
    }
    [Console]::Out.WriteLine(($reply | ConvertTo-Json -Depth 4 -Compress))
    [Console]::Out.Flush()
}
