<#
.SYNOPSIS
  Apply an OS-level deny-write rule to the Source Vault (Windows).

.DESCRIPTION
  Defence in depth ONLY. Continuum's own protection does not depend on this:
  a vault write is already unrepresentable in the type system (ADR-0001
  Layer 1) and unreachable through the storage abstraction (Layer 4).

  Continuum will never run this for you, and never verifies the result by
  attempting a write -- FOUNDATION_APPROVAL A-01 forbids Continuum from
  being the process that writes to the vault, even diagnostically. After
  running this, /health continues to report "not_verified" on Windows,
  because ACL enforcement cannot be observed without writing.

  Verify manually instead:  icacls "<vault path>"

.PARAMETER VaultPath
  The Source Vault root.
#>
param([Parameter(Mandatory = $true)][string]$VaultPath)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $VaultPath)) {
    Write-Error "Vault path does not exist: $VaultPath"
}

$account = "$env:USERDOMAIN\$env:USERNAME"
Write-Host "Applying deny-write for $account on $VaultPath" -ForegroundColor Cyan
Write-Host "You will still be able to write to it from an elevated shell or another account."
Write-Host ""

icacls $VaultPath /deny "${account}:(OI)(CI)(W,D,DC)"

Write-Host ""
Write-Host "Done. Verify with:  icacls `"$VaultPath`"" -ForegroundColor Green
Write-Host "To undo:            icacls `"$VaultPath`" /remove:d `"$account`""
