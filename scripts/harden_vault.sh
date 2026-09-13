#!/usr/bin/env bash
# Apply OS-level read-only protection to the Source Vault (POSIX).
#
# Defence in depth ONLY -- Continuum's protection does not depend on it, and
# Continuum never verifies it by writing (FOUNDATION_APPROVAL A-01).
set -euo pipefail

VAULT="${1:?usage: harden_vault.sh <vault-path>}"
[ -d "$VAULT" ] || { echo "Vault path does not exist: $VAULT" >&2; exit 1; }

echo "Two supported approaches:"
echo
echo "  1. Read-only bind mount (strongest):"
echo "       sudo mount --bind \"$VAULT\" \"$VAULT\""
echo "       sudo mount -o remount,ro,bind \"$VAULT\""
echo
echo "  2. Run Continuum as a user with no write permission:"
echo "       sudo chown -R vaultowner:vaultowner \"$VAULT\""
echo "       sudo chmod -R a-w \"$VAULT\""
echo
echo "After either, /health reports vault_protection=verified_readonly on POSIX."
