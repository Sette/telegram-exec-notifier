#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
unit_name="telegram-exec-notifier.service"
unit_dir="$HOME/.config/systemd/user"
environment_file="$HOME/.config/telegram-exec-notifier/environment.cred"

if [[ ! -f "$environment_file" ]]; then
  printf 'Credencial cifrada não encontrada: %s\n' "$environment_file" >&2
  printf 'Crie ~/.config/telegram-exec-notifier/environment com TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID e rode ./encrypt-credentials.sh.\n' >&2
  exit 1
fi

mkdir -p "$unit_dir"
sed "s|@PROJECT_DIR@|$project_dir|g" "$project_dir/systemd/$unit_name" > "$unit_dir/$unit_name"
chmod 0644 "$unit_dir/$unit_name"
chmod 0600 "$environment_file"

systemctl --user daemon-reload
systemctl --user enable "$unit_name"
systemctl --user restart "$unit_name"
systemctl --user status "$unit_name" --no-pager
