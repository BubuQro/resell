#!/usr/bin/env bash
# Archivo ejecutable con doble clic desde Finder en macOS
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
exec "$DIR/iniciar_servidor.sh"

