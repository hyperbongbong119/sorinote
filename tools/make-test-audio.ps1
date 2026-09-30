Add-Type -AssemblyName System.Speech
$folder = Join-Path (Split-Path $PSScriptRoot -Parent) 'tmp'
[IO.Directory]::CreateDirectory($folder) | Out-Null
$speech = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speech.SetOutputToWaveFile((Join-Path $folder 'synthetic-test.wav'))
    $speech.Speak('This is a software test meeting. We decided to launch the new website next Monday. Alex will prepare the checklist. The budget is still undecided.')
} finally {
    $speech.Dispose()
}
Write-Output 'Synthetic audio created. No microphone or system audio was recorded.'
