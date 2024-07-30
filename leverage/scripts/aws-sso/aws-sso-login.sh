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
SSO_PROFILE_NAME=${SSO_PROFILE_NAME:-$PROJECT-sso}
SSO_CACHE_DIR=${SSO_CACHE_DIR:-/home/leverage/tmp/$PROJECT/sso/cache}
AWS_SSO_CACHE_DIR=/home/leverage/.aws/sso/cache
SSO_TOKEN_FILE_NAME='token'
debug "SCRIPT_LOG_LEVEL=$SCRIPT_LOG_LEVEL"
debug "COMMON_CONFIG_FILE=$COMMON_CONFIG_FILE"
debug "ACCOUNT_CONFIG_FILE=$ACCOUNT_CONFIG_FILE"
debug "BACKEND_CONFIG_FILE=$BACKEND_CONFIG_FILE"
debug "SSO_PROFILE_NAME=$SSO_PROFILE_NAME"
debug "SSO_CACHE_DIR=$SSO_CACHE_DIR"
debug "SSO_TOKEN_FILE_NAME=$SSO_TOKEN_FILE_NAME"

# Make sure cache dir exists
mkdir -p "$SSO_CACHE_DIR"

# -----------------------------------------------------------------------------
# Log in
# -----------------------------------------------------------------------------
info "Logging in..."
aws sso login --profile "$SSO_PROFILE_NAME"

# Store token in cache
debug "Caching token"
TOKEN_FILE="$SSO_CACHE_DIR/$SSO_TOKEN_FILE_NAME"
FILES=$(find "$AWS_SSO_CACHE_DIR" -maxdepth 1 -type f -name '*.json' -not -name 'botocore-client*' -exec ls {} \;)
for file in $FILES;
do
    if (jq -er '.accessToken' $file >/dev/null);
    then
        cp $file "$TOKEN_FILE"
        break
    fi
done
debug "Token Expiration: $BOLD$(jq -r '.expiresAt' "$TOKEN_FILE")$RESET"

info "${BOLD}Successfully logged in!$RESET"
