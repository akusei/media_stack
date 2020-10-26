#!/bin/bash

statusCode=0
exitCode=1

while [[ ${statusCode} != 200 || ${exitCode} != 0 ]]; do
  echo "testing connection..."
  statusCode=$(curl -I -k --silent -w %{http_code} --output /dev/null https://www.google.com)
  exitCode=$?
  [[ ${statusCode} != 200 || ${exitCode} != 0 ]] && sleep 3s
done

exit 0
