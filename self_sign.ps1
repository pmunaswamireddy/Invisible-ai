# PowerShell Script to Self-Sign the Compiled Executable and Install the Root Certificate locally.
# This prevents Windows SmartScreen from blocking the application by verifying it as a trusted program.

param(
    [string]$exePath = "D:\invisibleai\dist\v5\SystemAudioEngine.exe"
)

# Auto-detect target executable under dist if not specified or not found
if ([string]::IsNullOrEmpty($exePath) -or -not (Test-Path $exePath)) {
    if (Test-Path "dist") {
        $found = Get-ChildItem -Path "dist" -Filter "SystemAudioEngine.exe" -Recurse | Select-Object -First 1
        if ($found) {
            $exePath = $found.FullName
        }
    }
}

# Check if running as Administrator (required to import certificates to Trusted Root Store)
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Elevating privileges... Spawning Administrator PowerShell window."
    $argsList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($exePath) {
        $argsList += " -exePath `"$exePath`""
    }
    Start-Process powershell -ArgumentList $argsList -Verb RunAs
    Exit 0
}

# Main Execution wrapped in Try/Catch to keep the elevated window open on success or failure
try {
    if (-not (Test-Path $exePath)) {
        throw "Could not locate target executable at path: $exePath. Please run build_exe.bat first."
    }

    Write-Host "=================================================="
    Write-Host "   Target: $exePath"
    Write-Host "   Generating Trusted Self-Signed Certificate...  "
    Write-Host "=================================================="

    # Create a self-signed certificate for Code Signing
    $certName = "CN=SystemAudioEngine Code Signing Certificate"
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $certName -CertStoreLocation "Cert:\CurrentUser\My" -FriendlyName "SystemAudioEngine Signing Cert" -NotAfter (Get-Date).AddYears(5)

    # Export the certificate
    $tempCertPath = "$env:TEMP\SystemAudioEngine.cer"
    Export-Certificate -Cert $cert -FilePath $tempCertPath | Out-Null

    Write-Host "Importing certificate into Trusted Root Certification Authorities..."
    # Import the certificate to the Local Machine Trusted Root store to establish system trust
    Import-Certificate -FilePath $tempCertPath -CertStoreLocation "Cert:\LocalMachine\Root" | Out-Null
    # Import the certificate to the Trusted Publishers store
    Import-Certificate -FilePath $tempCertPath -CertStoreLocation "Cert:\LocalMachine\TrustedPublisher" | Out-Null

    Write-Host "Signing the executable..."
    # Sign the compiled PyInstaller binary
    Set-AuthenticodeSignature -FilePath $exePath -Certificate $cert | Out-Null

    # Cleanup temporary certificate file
    Remove-Item $tempCertPath -Force -ErrorAction SilentlyContinue

    Write-Host "=================================================="
    Write-Host "   SUCCESS: Executable successfully signed!"
    Write-Host "   Windows SmartScreen will now recognize the binary."
    Write-Host "=================================================="
}
catch {
    Write-Error "An error occurred during execution: $_"
}
finally {
    Write-Host ""
    Read-Host "Press Enter to exit..."
}
