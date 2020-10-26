#!/bin/bash

set -o pipefail
set -o errexit
set -o nounset

readonly ROOT_DIR="$(readlink -f "$(dirname "$(realpath "$0")")/../")"


check_key_exists()
{
  if ! gpg --list-keys secrets &> /dev/null; then
    echo "secrets key does not exist, please generate a new GPG key pair named 'secrets'"
    return 1
  fi
  return 0
}

encrypt()
{
  declare force="${1}"

  if ! check_key_exists; then
    return 1
  fi

  if [[ ${force} == 'true' ]]; then
    force="--yes"
  else
    force=""
  fi

  echo encrypting secrets
  gpg --encrypt -a \
    --output "${ROOT_DIR}/vars/secrets.enc" \
    -u secrets -r secrets \
    ${force} \
    "${ROOT_DIR}/vars/secrets.yml"
}

decrypt()
{
  if ! check_key_exists; then
    return 1
  fi

  if [[ ${force} == 'true' ]]; then
    force="--yes"
  else
    force=""
  fi

  echo decrypting secrets
  gpg --decrypt \
    --output "${ROOT_DIR}/vars/secrets.yml" \
    ${force} \
    "${ROOT_DIR}/vars/secrets.enc"
}

show_help()
{
  echo "secrets double encryption tool"
  echo "used to encrypt already encrypted ansible vault files"
  echo
  echo "usage: secrets.sh <-e|--encrypt|-d|--decrypt> [--f|--force]"
  echo
  echo "   -e, --encrypt   encrypt the secrets file"
  echo "   -d, --decrypt   decrypt the secrets file"
  echo "   -f, --force     force overwritting of output file"

  return 1
}


if ! which gpg &> /dev/null; then
  echo "GnuPG is required for this script to run properly"
  exit 1
fi

declare command="show_help" force="false"

while [[ ! -z ${1:-} ]]; do
  case "${1:-}" in
  "-e"|"--encrypt")
    command="encrypt"
    ;;

  "-d"|"--decrypt")
    command="decrypt"
    ;;

  "-f"|"--force")
    force="true"
    ;;
  esac
  shift
done

${command} "${force}"
exit $?
