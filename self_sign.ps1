# PowerShell Script to Self-Sign the Compiled Executable and Install the Root Certificate locally.
# This prevents Windows SmartScreen from blocking the application by verifying it as a trusted program.

param(
    [string]$exePath = "dist/SystemAudioEngine.exe"
)

if (-not (Test-Path $exePath)) {
    Write-Error "Could not find target executable: $exePath. Please run build_exe.bat first."
    Exit 1
}

# Check if running as Administrator (required to import certificates to Trusted Root Store)
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "This script must be run as Administrator to install the certificate to the Trusted Root Store."
    Write-Host "Please open an Administrator PowerShell window and run this script."
    Pause
    Exit 1
}

Write-Host "=================================================="
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
