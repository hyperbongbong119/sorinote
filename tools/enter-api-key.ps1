Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$target = Join-Path (Split-Path $PSScriptRoot -Parent) '.env.local'
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Meeting Notes - OpenAI API key'
$form.ClientSize = New-Object System.Drawing.Size(620, 255)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$form.Font = New-Object System.Drawing.Font('Segoe UI', 10)
$label = New-Object System.Windows.Forms.Label
$label.Text = "Paste your existing OpenAI API key below.`r`nThe key stays hidden and is never sent to this chat."
$label.SetBounds(24, 20, 570, 48)
$form.Controls.Add($label)
$inputBox = New-Object System.Windows.Forms.TextBox
$inputBox.UseSystemPasswordChar = $true
$inputBox.SetBounds(24, 80, 570, 30)
$form.Controls.Add($inputBox)
$destination = New-Object System.Windows.Forms.Label
$destination.Text = "Save locally as OPENAI_API_KEY in:`r`n$target"
$destination.SetBounds(24, 122, 570, 52)
$form.Controls.Add($destination)
$save = New-Object System.Windows.Forms.Button
$save.Text = 'Save key'
$save.SetBounds(364, 194, 110, 36)
$form.Controls.Add($save)
$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancel'
$cancel.SetBounds(484, 194, 110, 36)
$cancel.Add_Click({ $form.Close() })
$form.Controls.Add($cancel)
$form.AcceptButton = $save
$form.CancelButton = $cancel
$save.Add_Click({
    $secret = $inputBox.Text.Trim()
    if ($secret -notmatch '^sk-[A-Za-z0-9_-]{20,}$') {
        [System.Windows.Forms.MessageBox]::Show('Enter a valid OpenAI API key beginning with sk-.', 'Check key') | Out-Null
        return
    }
    try {
        if (Test-Path -LiteralPath $target) {
            [System.Windows.Forms.MessageBox]::Show('An .env.local file already exists. Nothing was overwritten.', 'File exists') | Out-Null
            return
        }
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("OPENAI_API_KEY=$secret`n")
        $stream = [System.IO.File]::Open($target, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
        finally { $stream.Dispose(); [Array]::Clear($bytes, 0, $bytes.Length) }
        $inputBox.Clear()
        $secret = $null
        [System.Windows.Forms.MessageBox]::Show('Key saved locally. Return to Codex to continue.', 'Saved') | Out-Null
        $form.Close()
    } catch {
        [System.Windows.Forms.MessageBox]::Show('Could not save the key. No key value was logged.', 'Save failed') | Out-Null
    }
})
$form.Add_Shown({ $inputBox.Focus() })
[void]$form.ShowDialog()
$inputBox.Clear()
$form.Dispose()
