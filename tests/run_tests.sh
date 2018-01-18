#!/usr/bin/env bash
# Copyright 2017 Autodesk, Inc.  All rights reserved.
#
# Use of this software is subject to the terms of the Autodesk license agreement
# provided at the time of installation or download, or which otherwise accompanies
# this software in either electronic or hard copy form.
#
# Stop on errors
set -e
usage()
{
    echo "Usage : $0 [-h] [-p <tk-core path>] <test>"
    echo "Options :"
    echo " -h : show this help message"
    echo " -p : use tk-core from this path"
}

# Accept specific tk-core path from the command line or fall back to
# a default value
tk_core_path="../../tk-core"
while getopts "ht:p:" option
do
    case $option in
        h)
            usage
            exit 1
            ;;
        p)
            tk_core_path=$OPTARG
            echo "Will be using tk-core in ${tk_core_path}"
            # Remove this from the params send to tk-core tests
            shift $((OPTIND-1))
            ;;
        ?)
            usage
            exit 1
            ;;
    esac
done

# Check we can run tests
if [ ! -d ${tk_core_path} ]; then
  echo ""
  echo "ERROR: No tk-core found in path '${tk_core_path}'."
  echo ""
  echo "For options, run this command with a -h option."
  exit 1
fi

find .. -name "*.pyc" -delete
${tk_core_path}/tests/run_tests.sh --test-root . $*
