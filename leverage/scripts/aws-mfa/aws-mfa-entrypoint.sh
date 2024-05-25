#!/usr/bin/env bash

# -----------------------------------------------------------------------------
# - In a nutshell, what the script does is:
# -----------------------------------------------------------------------------
#   1. Figure out all the AWS profiles used by Terraform
#   2. For each profile:
#       2.1. Get the role, MFA serial number, and source profile
#       2.2. Figure out the OTP or prompt the user
#       2.3. Assume the role to create temporary credentials
#       2.4. Generate the AWS profiles config files
#   3. Pass the control back to the main process (e.g. Terraform)
# -----------------------------------------------------------------------------

set -o errexit
set -o pipefail
set -o nounset


# ---------------------------
# Formatting helpers
# ---------------------------
BOLD="\033[1m"
DATE="\033[0;90m"
ERROR="\033[41;37m"
INFO="\033[0;34m"
DEBUG="\033[0;32m"
RESET="\033[0m"

# ---------------------------
# Helper Functions
# ---------------------------

# Simple logging functions
function error { log "${ERROR}ERROR${RESET}\t$1" 0; }
function info { log "${INFO}INFO${RESET}\t$1" 1; }
function debug { log "${DEBUG}DEBUG${RESET}\t$1" 2; }
function log {
    if [[ $MFA_SCRIPT_LOG_LEVEL -gt "$2" ]]; then
        echo -e "${DATE}[$(date +"%H:%M:%S")]${RESET}   $1"
    fi
}

# Get the value of an entry in a config file
function get_config {
    local config_file=$1
    local config_key=$2
    local config_value=$(grep -oEi "^$config_key\s+=.*\"([a-zA-Z0-9\-]+)\"" $config_file \
                         | grep -oEi "\".+\"" \
                         | sed 's/\"//g')
    echo $config_value
}

# Get the value of an AWS profile attribute
function get_profile {
    local aws_config="$1"
    local aws_credentials="$2"
    local profile_name="$3"
    local profile_key="$4"
    local profile_value=$(AWS_CONFIG_FILE=$aws_config; \
                          AWS_SHARED_CREDENTIALS_FILE=$aws_credentials; \
                          aws configure get "profile.$profile_name.$profile_key")
    echo "$profile_value"
}


# -----------------------------------------------------------------------------
# Initialize variables
# -----------------------------------------------------------------------------
MFA_SCRIPT_LOG_LEVEL=$(printenv MFA_SCRIPT_LOG_LEVEL || echo 2)
BACKEND_CONFIG_FILE=$(printenv BACKEND_CONFIG_FILE)
COMMON_CONFIG_FILE=$(printenv COMMON_CONFIG_FILE)
SRC_AWS_CONFIG_FILE=$(printenv SRC_AWS_CONFIG_FILE)
SRC_AWS_SHARED_CREDENTIALS_FILE=$(printenv SRC_AWS_SHARED_CREDENTIALS_FILE)
TF_AWS_CONFIG_FILE=$(printenv AWS_CONFIG_FILE)
TF_AWS_SHARED_CREDENTIALS_FILE=$(printenv AWS_SHARED_CREDENTIALS_FILE)
AWS_CACHE_DIR=$(printenv AWS_CACHE_DIR || echo /tmp/cache)
AWS_REGION=$(get_config "$BACKEND_CONFIG_FILE" region)
AWS_OUTPUT=json
debug "${BOLD}BACKEND_CONFIG_FILE=${RESET}$BACKEND_CONFIG_FILE"
debug "${BOLD}SRC_AWS_CONFIG_FILE=${RESET}$SRC_AWS_CONFIG_FILE"
debug "${BOLD}SRC_AWS_SHARED_CREDENTIALS_FILE=${RESET}$SRC_AWS_SHARED_CREDENTIALS_FILE"
debug "${BOLD}TF_AWS_CONFIG_FILE=${RESET}$TF_AWS_CONFIG_FILE"
debug "${BOLD}TF_AWS_SHARED_CREDENTIALS_FILE=${RESET}$TF_AWS_SHARED_CREDENTIALS_FILE"
debug "${BOLD}AWS_REGION=${RESET}$AWS_REGION"
debug "${BOLD}AWS_OUTPUT=${RESET}$AWS_OUTPUT"


# -----------------------------------------------------------------------------
# Pre-run Steps
# -----------------------------------------------------------------------------

# Make some pre-validations
if [[ ! -f "$SRC_AWS_CONFIG_FILE" ]]; then
    error "Unable to find 'AWS Config' file in path: $SRC_AWS_CONFIG_FILE"
    exit 90
fi
if [[ ! -f "$SRC_AWS_SHARED_CREDENTIALS_FILE" ]]; then
    error "Unable to find 'AWS Credentials' file in path: $SRC_AWS_SHARED_CREDENTIALS_FILE"
    exit 91
fi

# Ensure cache credentials dir exists
mkdir -p "$AWS_CACHE_DIR"


# -----------------------------------------------------------------------------
# 1. Figure out all the AWS profiles used by Terraform
# -----------------------------------------------------------------------------

# Parse all available profiles in config.tf
RAW_PROFILES=()
if [[ -f "config.tf" ]] && PARSED_PROFILES=$(grep -v "lookup" config.tf | grep -E "^\s+profile"); then
    while IFS= read -r line ; do
        RAW_PROFILES+=("$(echo "$line" | sed 's/ //g' | sed 's/[\"\$\{\}]//g')")
    done <<< "$PARSED_PROFILES"
fi
# Some profiles may be found in local.tf also
if [[ -f "locals.tf" ]] && PARSED_PROFILES=$(grep -E "^\s+profile" locals.tf); then
    while IFS= read -r line ; do
        RAW_PROFILES+=("$(echo "$line" | sed 's/ //g' | sed 's/[\"\$\{\}]//g')")
    done <<< "$PARSED_PROFILES"
fi

set +e
# Now we need to replace any placeholders in the profiles
PROFILE_VALUE=$(get_config "$BACKEND_CONFIG_FILE" profile)
PROJECT_VALUE=$(get_config "$COMMON_CONFIG_FILE" project)
PROFILES=()
for i in "${RAW_PROFILES[@]}" ; do
    TMP_PROFILE=$(echo "$i" | sed "s/profile=//" | sed "s/var.profile/${PROFILE_VALUE}/" | sed "s/var.project/${PROJECT_VALUE}/")
    PROFILES+=("$TMP_PROFILE")
done

# And then we have to remove repeated profiles
UNIQ_PROFILES=($(echo "${PROFILES[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' '))
if [[ "${#UNIQ_PROFILES[@]}" -eq 0 ]]; then
    error "Unable to find any profiles in config.tf"
    exit 100
fi
info "${BOLD}MFA:${RESET} Found ${#UNIQ_PROFILES[@]} profile/s"


# -----------------------------------------------------------------------------
# 2. For each profile:
# -----------------------------------------------------------------------------
for i in "${UNIQ_PROFILES[@]}" ; do
    info "${BOLD}MFA:${RESET} Attempting to get temporary credentials for profile ${BOLD}$i${RESET}"

    # -----------------------------------------------------------------------------
    # 2.1. Get the role, serial number and source profile from AWS config file
    # -----------------------------------------------------------------------------
    if ! MFA_ROLE_ARN=$(AWS_CONFIG_FILE="$SRC_AWS_CONFIG_FILE" && \
                        AWS_SHARED_CREDENTIALS_FILE="$SRC_AWS_SHARED_CREDENTIALS_FILE" && \
                        aws configure get role_arn --profile "$i" 2>&1); then
        if [[ "$MFA_ROLE_ARN" == *"$i"* ]]; then
            error "Credentials for profile $i have not been properly configured. Please check your configuration."
            error "Check your AWS config file to look for the following profile entry: $i"
            error "Check the following link for possible solutions: https://leverage.binbash.co/user-guide/troubleshooting/credentials/"
        else
            error "Missing 'role_arn'"
        fi
        exit 150
    fi
    debug "${BOLD}MFA_ROLE_ARN=${RESET}$MFA_ROLE_ARN"
    MFA_SERIAL_NUMBER=$(get_profile "$SRC_AWS_CONFIG_FILE" "$SRC_AWS_SHARED_CREDENTIALS_FILE" "$i" mfa_serial)
    debug "${BOLD}MFA_SERIAL_NUMBER=${RESET}$MFA_SERIAL_NUMBER"
    MFA_PROFILE_NAME=$(get_profile "$SRC_AWS_CONFIG_FILE" "$SRC_AWS_SHARED_CREDENTIALS_FILE" "$i" source_profile)
    debug "${BOLD}MFA_PROFILE_NAME=${RESET}$MFA_PROFILE_NAME"
    # Validate all required fields
    if [[ $MFA_SERIAL_NUMBER == "" ]]; then error "Missing 'mfa_serial'" && exit 151; fi
    if [[ $MFA_PROFILE_NAME == "" ]]; then error "Missing 'source_profile'" && exit 152; fi

    # -----------------------------------------------------------------------------
    # 2.2. Figure out the OTP or prompt the user
    # -----------------------------------------------------------------------------
    # Loop a predefined number of times in case the OTP becomes invalid between
    # the time it is generated and the time it is provided to the script
    # -----------------------------------------------------------------------------
    MAX_RETRIES=3
    RETRIES_COUNT=0
    OTP_FAILED=true
    MFA_DURATION=3600
    TEMP_FILE="$AWS_CACHE_DIR/$i"
    debug "${BOLD}TEMP_FILE=${RESET}$TEMP_FILE"

    while [[ $OTP_FAILED == true && $RETRIES_COUNT -lt $MAX_RETRIES ]]; do

        #
        # Check if cached credentials exist: look for a file that correspond to
        #       the current profile
        #
        if [[ -f "$TEMP_FILE" ]] && EXPIRATION_DATE=$(jq -r '.Credentials.Expiration' "$TEMP_FILE"); then
            debug "Found cached credentials in ${BOLD}$TEMP_FILE${RESET}"

            # Get expiration date/timestamp
            EXPIRATION_DATE=$(echo "$EXPIRATION_DATE" | sed -e 's/T/ /' | sed -E 's/(Z|\+[0-9]{2}:[0-9]{2})$//')
            debug "${BOLD}EXPIRATION_DATE=${RESET}$EXPIRATION_DATE"
            EXPIRATION_TS=$(date -d "$EXPIRATION_DATE" +"%s" || date +"%s")
            debug "${BOLD}EXPIRATION_TS=${RESET}$EXPIRATION_TS"

            # Compare current timestamp (plus a margin) with the expiration timestamp
            CURRENT_TS=$(date +"%s")
            CURRENT_TS_PLUS_MARGIN=$(( "$CURRENT_TS" + (30 * 60) ))
            debug "${BOLD}CURRENT_TS=${RESET}$CURRENT_TS"
            debug "${BOLD}CURRENT_TS_PLUS_MARGIN=${RESET}$CURRENT_TS_PLUS_MARGIN"
            if [[ CURRENT_TS_PLUS_MARGIN -lt $EXPIRATION_TS ]]; then
                info "${BOLD}MFA:${RESET} Using cached credentials"

                # Pretend the OTP succeeded and exit the while loop
                OTP_FAILED=false
                break
            fi
        fi

        # Prompt user for MFA Token
        echo -ne "${BOLD}MFA:${RESET} Please type in your OTP: "
        if ! MFA_TOKEN_CODE=$(read MFA_TOKEN_CODE && echo "$MFA_TOKEN_CODE"); then
            echo
            error "Aborted!"
            exit 156;
        fi
        debug "${BOLD}MFA_TOKEN_CODE=${RESET}$MFA_TOKEN_CODE"

        # -----------------------------------------------------------------------------
        # 2.3. Assume the role to generate the temporary credentials
        # -----------------------------------------------------------------------------
        MFA_ROLE_SESSION_NAME="$MFA_PROFILE_NAME-temp"
        if ! MFA_ASSUME_ROLE_OUTPUT=$(AWS_CONFIG_FILE="$SRC_AWS_CONFIG_FILE" && \
                                      AWS_SHARED_CREDENTIALS_FILE="$SRC_AWS_SHARED_CREDENTIALS_FILE" && \
                                      aws sts assume-role \
                                                --role-arn "$MFA_ROLE_ARN" \
                                                --serial-number "$MFA_SERIAL_NUMBER" \
                                                --role-session-name "$MFA_ROLE_SESSION_NAME" \
                                                --duration-seconds "$MFA_DURATION" \
                                                --token-code "$MFA_TOKEN_CODE" \
                                                --profile "$MFA_PROFILE_NAME" 2>&1); then
            # Check if STS call failed because of invalid token or user interruption
            if [[ $MFA_ASSUME_ROLE_OUTPUT == *"invalid MFA"* ]]; then
                OTP_FAILED=true
                info "Unable to get valid credentials. Let's try again..."
            elif [[ $MFA_ASSUME_ROLE_OUTPUT == *"Invalid length for parameter TokenCode, value:"* ]]; then
                OTP_FAILED=true
                info "Invalid token length, it must be 6 digits long. Let's try again..."
            elif [[ $MFA_ASSUME_ROLE_OUTPUT == *"AccessDenied"* ]]; then
                info "Access Denied error!"
                exit 161
            elif [[ $MFA_ASSUME_ROLE_OUTPUT == *"An error occurred"* ]]; then
                info "An error occurred!"
                exit 162
            fi
            debug "${BOLD}MFA_ASSUME_ROLE_OUTPUT=${RESET}${MFA_ASSUME_ROLE_OUTPUT}"
        else
            OTP_FAILED=false
            echo "$MFA_ASSUME_ROLE_OUTPUT" > "$TEMP_FILE"
        fi
        debug "${BOLD}OTP_FAILED=${RESET}$OTP_FAILED"
        RETRIES_COUNT=$((RETRIES_COUNT+1))
        debug "${BOLD}RETRIES_COUNT=${RESET}$RETRIES_COUNT"

    done

    # Check if credentials were actually created
    if [[ $OTP_FAILED == true ]]; then
        error "Unable to get valid credentials after $MAX_RETRIES attempts"
        exit 160
    fi

    # -----------------------------------------------------------------------------
    # 2.4. Generate the AWS profiles config files
    # -----------------------------------------------------------------------------

    # Parse id, secret and session from the output above
    AWS_ACCESS_KEY_ID=$(jq -r .Credentials.AccessKeyId "$TEMP_FILE")
    AWS_SECRET_ACCESS_KEY=$(jq -r .Credentials.SecretAccessKey "$TEMP_FILE")
    AWS_SESSION_TOKEN=$(jq -r .Credentials.SessionToken "$TEMP_FILE")
    debug "${BOLD}AWS_ACCESS_KEY_ID=${RESET}${AWS_ACCESS_KEY_ID:0:4}**************"
    debug "${BOLD}AWS_SECRET_ACCESS_KEY=${RESET}${AWS_SECRET_ACCESS_KEY:0:4}**************"
    debug "${BOLD}AWS_SESSION_TOKEN=${RESET}${AWS_SESSION_TOKEN:0:4}**************"

    # Create a profile block in the AWS credentials file using the credentials above
    (AWS_CONFIG_FILE=$TF_AWS_CONFIG_FILE; \
    AWS_SHARED_CREDENTIALS_FILE=$TF_AWS_SHARED_CREDENTIALS_FILE; \
    aws configure set "profile.$i.aws_access_key_id" "$AWS_ACCESS_KEY_ID"; \
    aws configure set "profile.$i.aws_secret_access_key" "$AWS_SECRET_ACCESS_KEY"; \
    aws configure set "profile.$i.aws_session_token" "$AWS_SESSION_TOKEN"; \
    aws configure set region "$AWS_REGION"; \
    aws configure set output "$AWS_OUTPUT")

    info "${BOLD}MFA:${RESET} Credentials written succesfully!"
done

# -----------------------------------------------------------------------------
# 3. Pass the control back to the main process
# -----------------------------------------------------------------------------
exec "$@"
