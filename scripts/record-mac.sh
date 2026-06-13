#!/usr/bin/env bash
set -euo pipefail

if [[ "${RECORD_MAC_TRACE:-false}" == "true" ]]; then
  set -x
fi

###############################################################################
# privledger record-mac.sh
###############################################################################

STOP_SENT=""

on_stop() {
  # Idempotence guard ensures the stop note is emitted once. avcam-cli runs in
  # the foreground so terminal/process-group SIGINT reaches it directly.
  if [[ -n "${STOP_SENT}" ]]; then return; fi
  STOP_SENT=1

  echo "[record-mac] Graceful stop requested" | tee -a "${LOG_FILE:-/dev/null}"
}

trap on_stop INT TERM

###############################################################################
# Paths
###############################################################################

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VLOG_DIR="${ROOT_DIR}/vlog"
LOG_DIR="${ROOT_DIR}/logs"

mkdir -p "${VLOG_DIR}"
mkdir -p "${LOG_DIR}"

TIMESTAMP="${TIMESTAMP:-$(date -u +%Y-%m-%d-%H%M)}"
OUT_FILE="${VLOG_DIR}/${TIMESTAMP}.mov"
TMP_FILE="${VLOG_DIR}/${TIMESTAMP}.tmp.$$.mov"
BAD_FILE="${OUT_FILE}.bad.mov"
LOG_FILE="${LOG_DIR}/${TIMESTAMP}-record.log"

echo "[record-mac] Starting capture at ${TIMESTAMP}" | tee -a "${LOG_FILE}"

###############################################################################
# Configuration
###############################################################################

AVCAM_CLI="${AVCAM_CLI:-${ROOT_DIR}/tools/avcam-cli/.build/release/avcam-cli}"
AVCAM_CLI_DIR="$(cd "$(dirname "${AVCAM_CLI}")" && pwd)"
AVCAM_CLI_BIN="$(basename "${AVCAM_CLI}")"
AVCAM_CAMERA="${AVCAM_CAMERA:-Brio}"
AVCAM_AUDIO="${AVCAM_AUDIO:-Brio}"
AVCAM_AUDIO_CODEC="${AVCAM_AUDIO_CODEC:-alac}"
AVCAM_FORMAT_INDEX="${AVCAM_FORMAT_INDEX:-35}"
AVCAM_FPS="${AVCAM_FPS:-30}"
AVCAM_FINALIZE_TIMEOUT="${AVCAM_FINALIZE_TIMEOUT:-5}"

###############################################################################
# Helper: mark artifact without deleting
###############################################################################

finalize_bad() {
  local reason="$1"

  echo "[record-mac] Marking recording bad: ${reason}" | tee -a "${LOG_FILE}"

  if [[ -f "${TMP_FILE}" ]]; then
    mv "${TMP_FILE}" "${BAD_FILE}" || true
  fi

  exit 1
}

###############################################################################
# Preflight checks
###############################################################################

if [[ ! -x "${AVCAM_CLI}" ]]; then
  echo "[record-mac] ERROR: avcam-cli missing or not executable: ${AVCAM_CLI}" | tee -a "${LOG_FILE}"
  exit 1
fi

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "[record-mac] ERROR: ffprobe not found" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ -f "${OUT_FILE}" || -f "${BAD_FILE}" ]]; then
  echo "[record-mac] ERROR: output artifact already exists for ${TIMESTAMP}" | tee -a "${LOG_FILE}"
  exit 1
fi

###############################################################################
# Run avcam-cli.
#
# Keep this in the foreground and attached to the terminal. On macOS,
# AVFoundation camera permission can be denied when the unsigned CLI is launched
# with redirected output from a wrapper. Terminal-attached execution preserves
# the same capture permission behavior as direct avcam-cli invocation.
###############################################################################

AVCAM_CMD=(
  "./${AVCAM_CLI_BIN}"
  record
  --camera "${AVCAM_CAMERA}"
  --audio "${AVCAM_AUDIO}"
  --audio-codec "${AVCAM_AUDIO_CODEC}"
  --format-index "${AVCAM_FORMAT_INDEX}"
  --fps "${AVCAM_FPS}"
  --finalize-timeout "${AVCAM_FINALIZE_TIMEOUT}"
  --out "${TMP_FILE}"
)

if [[ -n "${AVCAM_SECONDS:-}" ]]; then
  AVCAM_CMD+=(--seconds "${AVCAM_SECONDS}")
fi

set +e
pushd "${AVCAM_CLI_DIR}" >/dev/null
"${AVCAM_CMD[@]}"
AVCAM_EXIT=$?
popd >/dev/null
set -e

###############################################################################
# Validate recorder exit
###############################################################################

if [[ ${AVCAM_EXIT} -ne 0 ]]; then
  finalize_bad "avcam-cli exit ${AVCAM_EXIT}"
fi

###############################################################################
# Basic file sanity
###############################################################################

if [[ ! -s "${TMP_FILE}" ]]; then
  finalize_bad "empty file"
fi

sleep 1

###############################################################################
# Duration sanity check
###############################################################################

DURATION="$(
  ffprobe -v error \
    -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 \
    "${TMP_FILE}" 2>/dev/null || true
)"

if [[ "${DURATION}" == "N/A" || -z "${DURATION}" ]]; then
  echo "[record-mac] Duration unavailable, accepting based on container integrity" | tee -a "${LOG_FILE}"
else
  if awk "BEGIN {exit !(${DURATION} > 0.5)}"; then
    :
  else
    finalize_bad "too short ${DURATION}"
  fi
fi

###############################################################################
# Stream sanity check
###############################################################################

ffprobe -v error \
  -show_entries stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,pix_fmt,duration,sample_rate,channels \
  -of default=nw=1 \
  "${TMP_FILE}" >> "${LOG_FILE}" 2>&1 || finalize_bad "ffprobe stream check failed"

###############################################################################
# Atomic finalize (good path)
###############################################################################

mv "${TMP_FILE}" "${OUT_FILE}"

echo "[record-mac] Capture complete -> ${OUT_FILE}" | tee -a "${LOG_FILE}"
echo "[record-mac] Duration: ${DURATION}s" | tee -a "${LOG_FILE}"

exit 0
