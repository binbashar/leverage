#!/usr/bin/env bash

set -o errexit
set -o pipefail
set -o nounset

# -----------------------------------------------------------------------------
# Formatting helpers
# -----------------------------------------------------------------------------
BOLD="\033[1m"
DATE="\033[0;90m"
ERROR="\033[41;37m"
INFO="\033[0;34m"
DEBUG="\033[0;32m"
RESET="\033[0m"

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
# Simple logging functions
function error { log "${ERROR}ERROR${RESET}\t$1" 0; }
function info { log "${INFO}INFO${RESET}\t$1" 1; }
function debug { log "${DEBUG}DEBUG${RESET}\t$1" 2; }
function log {
    if [[ $SCRIPT_LOG_LEVEL -gt $2 ]]; then
        printf "%b[%(%T)T]%b    %b\n" "$DATE" "$(date +%s)" "$RESET" "$1"
    fi
}

# -----------------------------------------------------------------------------
# Initialize variables
# -----------------------------------------------------------------------------
SCRIPT_LOG_LEVEL=${SCRIPT_LOG_LEVEL:-2}
PROJECT=$(hcledit -f "$COMMON_CONFIG_FILE" attribute get project | sed 's/"//g')
SSO_CACHE_DIR=${SSO_CACHE_DIR:-/home/leverage/tmp/$PROJECT/sso/cache}
debug "SCRIPT_LOG_LEVEL=$SCRIPT_LOG_LEVEL"
debug "AWS_SHARED_CREDENTIALS_FILE=$AWS_SHARED_CREDENTIALS_FILE"
debug "AWS_CONFIG_FILE=$AWS_CONFIG_FILE"
debug "SSO_CACHE_DIR=$SSO_CACHE_DIR"
debug "PROJECT=$PROJECT"

# -----------------------------------------------------------------------------
# Log out
# -----------------------------------------------------------------------------
aws sso logout

# Clear sso token
debug "Removing SSO Tokens."
rm -f $SSO_CACHE_DIR/*

# Clear AWS CLI credentials
debug "Wiping current SSO credentials."
awk '/^\[/{if($0~/profile '"$PROJECT-sso"'/ || $0 == "[default]"){found=1}else{found=""}} found' "$AWS_CONFIG_FILE" > tempconf && mv tempconf "$AWS_CONFIG_FILE"

rm -f "$AWS_SHARED_CREDENTIALS_FILE"

debug "All credentials wiped!"
