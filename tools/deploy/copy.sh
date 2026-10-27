#!/bin/bash -x
SOURCE_DIR=$(readlink -f "$(dirname ${BASH_SOURCE[0]})/../..")

if [ $# -lt 1 ]
then
  BUILD_DIR=$(find $SOURCE_DIR -maxdepth 1 -name 'build_*' -type d | grep -v 'build_ccls'  | head -1)
  if [[ "$BUILD_DIR" == "" ]]
  then
    echo "Usage ./copy.sh [oceanbase_dev_dir]"
  else
    echo "Choose $BUILD_DIR as build directory of oceanbase."
  fi
else
  BUILD_DIR=$1
fi

if [[ "$BUILD_DIR" == "" || ! -d "$BUILD_DIR" ]]
then
  echo "Build directory not found: '$BUILD_DIR'" 1>&2
  exit 1
fi

BIN_DIR=`pwd`/bin${VER}
LIB_DIR=`pwd`/lib
TOOL_DIR=`pwd`/tools
ETC_DIR=`pwd`/etc
DEBUG_DIR=`pwd`/debug
ADMIN_DIR=`pwd`/admin

function do_install {
  local install_status
  quiet=false
  if [ $# -eq 3 ] && [[ "$3" == "true" ]]
  then
    quiet=true
  fi
  [[ "$quiet" == "false" ]] && echo -n "Installing $1 "
  sources=$(ls $1 2>/dev/null)
  if [[ "$sources" == "" ]]
  then
    if [ "$quiet" == "false" ]
    then
      echo -e "\033[0;31mFAIL\033[0m\nNo such file: $1"
      return 1
    fi
    return 0
  fi
  target=$2
  # libtool only copies these files here; fall back to cp when libtool is not
  # installed (for example on the GitHub Ubuntu runner).
  if [[ "$(uname -s)" == "Darwin" ]] || ! command -v libtool >/dev/null 2>&1
  then
    err_msg=$(cp -f $sources $target 2>&1 >/dev/null)
  else
    err_msg=$(libtool --mode=install cp $sources $target 2>&1 >/dev/null)
  fi
  install_status=$?
  if [ $install_status -eq 0 ]
  then
    [[ "$quiet" == "false" ]] && echo -e "\033[0;32mOK\033[0m"
    return 0
  fi
  if [ "$quiet" == "false" ]
  then
    echo -e "\033[0;31mFAIL\033[0m\n$err_msg"
    return 1
  fi
  echo "Skipping optional $1: $err_msg" 1>&2
  return 0
}

if [ $# -lt 2 ]
then
  mkdir -p $BIN_DIR || exit 1
  mkdir -p $LIB_DIR || exit 1
  mkdir -p $TOOL_DIR || exit 1
  mkdir -p $ETC_DIR || exit 1
  mkdir -p $DEBUG_DIR || exit 1
  mkdir -p $ADMIN_DIR || exit 1

  exit_status=0
  do_install $BUILD_DIR/src/observer/seekdb $BIN_DIR/seekdb || exit_status=1
  do_install "$BUILD_DIR/syspack_release/*" $ADMIN_DIR || exit_status=1
  do_install $SOURCE_DIR/deps/3rd/usr/local/oceanbase/devtools/bin/llvm-symbolizer $TOOL_DIR/ || exit_status=1
  do_install $SOURCE_DIR/rpm/.dep_create/lib/libstdc++.so.6 $LIB_DIR true || exit_status=1
  do_install "$SOURCE_DIR/tools/timezone_V1.log" $ETC_DIR || exit_status=1
  do_install $SOURCE_DIR/deps/oblib/src/lib/profile/obperf $TOOL_DIR/ true || exit_status=1
  do_install $SOURCE_DIR/deps/3rd/home/admin/oceanbase/bin/obshell $BIN_DIR/obshell true || exit_status=1
  do_install "$SOURCE_DIR/tools/default_srs_data_mysql.sql" $ETC_DIR || exit_status=1
  exit $exit_status
fi
