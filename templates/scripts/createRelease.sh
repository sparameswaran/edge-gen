#!/bin/bash
#set -xv

function realpath() {
      [[ $1 = /* ]] && echo "$1" || echo "$PWD/${1#./}"
}

SCRIPT=$(realpath $0)
SCRIPT_DIR=$(dirname $SCRIPT)
ROOT_DIR=$SCRIPT_DIR/..

if [ "$#" -lt 1 ]; then

  echo "Usage: <release-directory>"
  echo " 1std arg: release directory containing the bosh release artifacts" 
  echo ""
  exit -1
fi

RELEASE_DIR=$(realpath $1)

PRODUCT_NAME={{product['short_name']}}
RELEASE_NAME={{product['short_name']}}-release
SERVICE_ADAPTER_RELEASE_VERSION={{version}}

cd $RELEASE_DIR

# Uncomment if the jobs have to be generated each time
rm -rf .dev_releases *releases .*builds  ~/.bosh/cache
bosh create release --with-tarball --name $RELEASE_NAME \
     --version $SERVICE_ADAPTER_RELEASE_VERSION --force
