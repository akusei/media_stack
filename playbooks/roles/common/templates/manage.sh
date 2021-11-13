#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail


readonly BASE_DIR="{{ common_install_root }}"


for d in ${BASE_DIR}/*/; do
  cd "${d}"
  docker-compose $@
done
