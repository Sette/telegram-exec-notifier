#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
unit_name="telegram-exec-notifier.service"
unit_dir="$HOME/.config/systemd/user"
environment_file="$HOME/.config/telegram-exec-notifier/environment"

if [[ ! -f "$environment_file" ]]; then
  printf 'Arquivo de configuração não encontrado: %s\n' "$environment_file" >&2
  printf 'Crie-o com TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID antes de iniciar o serviço.\n' >&2
  exit 1
fi

install -D -m 0644 "$project_dir/systemd/$unit_name" "$unit_dir/$unit_name"
chmod 0600 "$environment_file"

systemctl --user daemon-reload
systemctl --user enable "$unit_name"
systemctl --user restart "$unit_name"
systemctl --user status "$unit_name" --no-pager
