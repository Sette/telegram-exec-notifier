#!/usr/bin/env bash
# Encrypt the plain environment file with systemd-creds (host key + TPM2) and remove the plain copy.
set -euo pipefail

config_dir="$HOME/.config/telegram-exec-notifier"
plain="$config_dir/environment"
encrypted="$config_dir/environment.cred"

if [[ ! -f "$plain" ]]; then
  printf 'Arquivo não encontrado: %s\n' "$plain" >&2
  exit 1
fi

systemd-creds encrypt --user --with-key=host+tpm2 --name=environment "$plain" "$encrypted"
chmod 0600 "$encrypted"

# Only remove the plain file if the encrypted copy decrypts to the same content.
if systemd-creds decrypt --user --name=environment "$encrypted" - | cmp -s - "$plain"; then
  shred -u "$plain"
  printf 'Credenciais cifradas em %s; arquivo em texto puro removido.\n' "$encrypted"
else
  printf 'Falha ao verificar o arquivo cifrado; o original foi mantido.\n' >&2
  exit 1
fi
