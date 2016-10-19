#!/bin/bash
#set -xv

function realpath() {
      [[ $1 = /* ]] && echo "$1" || echo "$PWD/${1#./}"
}

SCRIPT=$(realpath $0)
SCRIPT_DIR=$(dirname $SCRIPT)
ROOT_DIR=$SCRIPT_DIR/..

if [ "$#" -lt 2 ]; then

  echo "Usage: <release-directory> <output-directory>"
  echo " 1st arg: absolute path to release directory to generate the bosh release "
  echo " 2nd arg: output directory to generate the tile metadata and pivotal tile"
  echo ""
  echo " Check sample props files under ${SCRIPT_DIR}/templates folder for creating the input files"
  exit -1
fi

RELEASE_DIR=$(realpath $1)
OUTPUT_DIR=$(realpath $2)
TEMPLATES_DIR=$ROOT_DIR/tile-templates

# Source the product properties

PRODUCT_NAME={{product['name']}}
PRODUCT_VERSION={{version}}
RELEASE_NAME={{product['release_name']}}
RELEASE_VERSION={{version}}

$SCRIPT_DIR/createRelease.sh $RELEASE_DIR 

TILE_FILE_FULL_PATH=`ls $TEMPLATES_DIR/*tile.yml`
RELEASE_TARFILE=`ls $RELEASE_DIR/*releases/*/*.tgz`
TILE_FILE_NAME=`basename $TILE_FILE_FULL_PATH`

rm -rf $OUTPUT_DIR/tmp
mkdir -p $OUTPUT_DIR/tmp
pushd $OUTPUT_DIR/tmp

mkdir -p metadata releases  migrations/v1
migrations_timestamp=`date +"%Y%m%d%H%M"`

cp $TEMPLATES_DIR/*migration.js migrations/v1/${migrations_timestamp}_migration.js
cp $TILE_FILE_FULL_PATH metadata/$TILE_FILE_NAME
cp $RELEASE_TARFILE releases/

# Ignore bundling the stemcell as most often the Ops Mgr carries the stemcell.
# If Ops Mgr complains of missing stemcell, change the version specified inside the tile to the one that Ops mgr knows about

zip -r ${PRODUCT_NAME}-v${PRODUCT_VERSION}.pivotal metadata releases migrations
mv ${PRODUCT_NAME}-v${PRODUCT_VERSION}.pivotal ..
popd
echo "Created Tile:  $OUTPUT_DIR/${PRODUCT_NAME}-v${PRODUCT_VERSION}.pivotal "
echo ""
