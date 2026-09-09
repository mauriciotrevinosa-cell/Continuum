# Continuum source Vault scaffold — directories only, idempotent, non-destructive.
# Creates nothing but folders. Never deletes, renames, moves or writes files
# inside C:\ContinuumVault.

param(
    # The Vault lives OUTSIDE this repository on purpose. Never point this
    # at a path inside the working tree: it will hold licensed source media
    # that must never reach version control, and Continuum treats it as
    # read-only once sources are registered.
    [string]$VaultRoot  = 'C:\ContinuumVault',
    # Reports are application-managed metadata and stay out of the Vault.
    [string]$ReportPath = 'C:\ContinuumData\vault-scaffold-report.txt'
)

$ErrorActionPreference = 'Stop'

# Ordered: franchise folder name -> source media folders.
# "fan-art" is appended to every entry automatically.
$Pool = [ordered]@{
  # --- FAVORITES (17) ---
  'Bocchi the Rock!'                                              = @('manga','anime')
  'Dandadan'                                                      = @('manga','anime')
  'SPY x FAMILY'                                                  = @('manga','anime')
  'Witch Hat Atelier'                                             = @('manga','anime')
  'Solo Leveling'                                                 = @('web-novel','manhwa','anime')
  'Jujutsu Kaisen'                                                = @('manga','anime')
  'Jujutsu Kaisen Modulo'                                         = @('manga')
  "Frieren - Beyond Journey's End"                                = @('manga','anime')
  'The Apothecary Diaries'                                        = @('light-novel','manga','anime')
  'That Time I Got Reincarnated as a Slime'                       = @('web-novel','light-novel','manga','anime')
  'Gachiakuta'                                                    = @('manga','anime')
  "Miss Kobayashi's Dragon Maid"                                  = @('manga','anime')
  'Call of the Night'                                             = @('manga','anime')
  'Dealing with Mikadono Sisters Is a Breeze'                     = @('manga','anime')
  'My Dress-Up Darling'                                           = @('manga','anime')
  "Komi Can't Communicate"                                        = @('manga','anime')
  'My Deer Friend Nokotan'                                        = @('manga','anime')

  # --- LIKES (22) ---
  'Sakamoto Days'                                                 = @('manga','anime')
  'Attack on Titan'                                               = @('manga','anime')
  'With You and the Rain'                                         = @('manga','anime')
  'Chainsaw Man'                                                  = @('manga','anime')
  'Smoking Behind the Supermarket with You'                       = @('manga','anime')
  'You and I Are Polar Opposites'                                 = @('manga','anime')
  'I Made Friends with the Second Prettiest Girl in My Class'     = @('web-novel','light-novel','manga','anime')
  "The Brilliant Healer's New Life in the Shadows"                = @('web-novel','light-novel','manga','anime')
  'MarriageToxin'                                                 = @('manga','anime')
  'Food for the Soul'                                             = @('anime','manga')
  'The Angel Next Door Spoils Me Rotten'                          = @('web-novel','light-novel','manga','anime')
  'Alya Sometimes Hides Her Feelings in Russian'                  = @('light-novel','manga','anime')
  "BOFURI - I Don't Want to Get Hurt, so I'll Max Out My Defense" = @('web-novel','light-novel','manga','anime')
  "Lil' Miss Vampire Can't Suck Right"                            = @('manga','anime')
  'KonoSuba'                                                      = @('web-novel','light-novel','manga','anime')
  'Tokyo Ghoul'                                                   = @('manga','anime')
  'Rich Girl Caretaker'                                           = @('web-novel','light-novel','manga','anime')
  'Oh Boy, Was I Wrong About Her'                                 = @('web-novel','light-novel','manga','anime')
  'Horimiya'                                                      = @('manga','anime')
  'The 100 Girlfriends Who Really, Really, Really, Really, Really Love You' = @('manga','anime')
  'Kagurabachi'                                                   = @('manga')
  'Haimiya-senpai Is Scary and Cute'                              = @('manga')

  # --- MEH (10) ---
  'Kaguya-sama - Love Is War'                                     = @('manga','anime')
  'The Quintessential Quintuplets'                                = @('manga','anime')
  'The Healer Who Was Banished from His Party, Is, in Fact, the Strongest' = @('web-novel','light-novel','manga','anime')
  "Welcome to the Outcast's Restaurant!"                          = @('web-novel','light-novel','manga','anime')
  'Dr. STONE'                                                     = @('manga','anime')
  'MASHLE - Magic and Muscles'                                    = @('manga','anime')
  "My Status as an Assassin Obviously Exceeds the Hero's"         = @('web-novel','light-novel','manga','anime')
  'Am I Actually the Strongest'                                   = @('web-novel','light-novel','manga','anime')
  'My Ridiculous Reincarnation'                                   = @('web-novel','light-novel','anime')
  'The Unaware Atelier Master'                                    = @('web-novel','light-novel','manga','anime')
}

$created  = New-Object System.Collections.Generic.List[string]
$existing = New-Object System.Collections.Generic.List[string]

function Ensure-Dir([string]$Path) {
  if (Test-Path -LiteralPath $Path) {
    $script:existing.Add($Path)
  } else {
    New-Item -ItemType Directory -Path $Path | Out-Null
    $script:created.Add($Path)
  }
}

Ensure-Dir $VaultRoot

foreach ($name in $Pool.Keys) {
  $fdir = Join-Path $VaultRoot $name
  Ensure-Dir $fdir
  foreach ($m in ($Pool[$name] + @('fan-art'))) {
    Ensure-Dir (Join-Path $fdir $m)
  }
}

Write-Output "franchises_declared=$($Pool.Count)"
Write-Output "dirs_created=$($created.Count)"
Write-Output "dirs_already_present=$($existing.Count)"

# --- verification -----------------------------------------------------------
$franchiseDirs = Get-ChildItem -LiteralPath $VaultRoot -Directory | Sort-Object Name
Write-Output "franchise_dirs_on_disk=$($franchiseDirs.Count)"

$files = Get-ChildItem -LiteralPath $VaultRoot -File -Recurse -Force -ErrorAction SilentlyContinue
Write-Output "files_anywhere_in_vault=$(@($files).Count)"

$edge = $franchiseDirs | Where-Object { $_.Name -match 'Edgerunners|Cyberpunk' }
Write-Output "cyberpunk_edgerunners_present=$(@($edge).Count -gt 0)"

# --- report -----------------------------------------------------------------
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('Continuum source Vault - scaffold report')
$lines.Add("Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')")
$lines.Add("Root: $VaultRoot")
$lines.Add('')
$lines.Add("Franchise folders declared : $($Pool.Count)")
$lines.Add("Franchise folders on disk  : $($franchiseDirs.Count)")
$lines.Add("Directories created        : $($created.Count)")
$lines.Add("Directories already present: $($existing.Count)")
$lines.Add("Files inside the Vault     : $(@($files).Count)")
$lines.Add("Cyberpunk: Edgerunners     : $(if (@($edge).Count -gt 0) {'PRESENT (unexpected)'} else {'not created (correct)'})")
$lines.Add('')
$lines.Add('DIRECTORY TREE (directories only)')
$lines.Add($VaultRoot)
foreach ($f in $franchiseDirs) {
  $lines.Add("  $($f.Name)")
  foreach ($s in (Get-ChildItem -LiteralPath $f.FullName -Directory | Sort-Object Name)) {
    $lines.Add("    $($s.Name)")
  }
}
$lines.Add('')
$lines.Add('MEDIA MAP')
foreach ($name in $Pool.Keys) {
  $lines.Add(("  {0} -> {1}" -f $name, (($Pool[$name] + @('fan-art')) -join ', ')))
}

Set-Content -LiteralPath $ReportPath -Value $lines -Encoding utf8
Write-Output "report_written=$ReportPath"
