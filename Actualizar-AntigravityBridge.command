#!/bin/bash
bash "$(dirname "$0")/update.sh" || echo "Ocurrio un error durante la actualizacion."
read -r -p "Pulsa Enter para cerrar..."
