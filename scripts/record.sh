#!/usr/bin/env bash
set -euo pipefail
set -x

###############################################################################
# privledger record.sh
###############################################################################

FF_PID=""
STOP_SENT=""

on_int() {
  # Idempotence guard — ensures exactly one graceful stop is issued
  if [[ -n "${STOP_SENT}" ]]; then return; fi
  STOP_SENT=1

  echo "[record] Graceful stop requested (sending 'q')" | tee -a "${LOG_FILE:-/dev/null}"
  if [[ -n "${FF_PID}" ]] && kill -0 "${FF_PID}" 2>/dev/null; then
    printf 'q\n' > "/proc/${FF_PID}/fd/0" 2>/dev/null || true
  fi
}

trap on_int INT

###############################################################################
# Required environment
###############################################################################

VIDEO_DEV="${VIDEO_DEV:?VIDEO_DEV not set}"
AUDIO_SRC="${AUDIO_SRC:?AUDIO_SRC not set}"
VAAPI_DEV="${VAAPI_DEV:?VAAPI_DEV not set}"

###############################################################################
# Paths
###############################################################################

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VLOG_DIR="${ROOT_DIR}/vlog"
LOG_DIR="${ROOT_DIR}/logs"

mkdir -p "${VLOG_DIR}"
mkdir -p "${LOG_DIR}"

TIMESTAMP="${TIMESTAMP:?TIMESTAMP not set}"
OUT_FILE="${VLOG_DIR}/${TIMESTAMP}.mkv"
TMP_FILE="${OUT_FILE}.tmp.$$"
LOG_FILE="${LOG_DIR}/${TIMESTAMP}-record.log"

echo "[record] Starting capture at ${TIMESTAMP}" | tee -a "${LOG_FILE}"

###############################################################################
# Helper: mark artifact without deleting
###############################################################################

finalize_bad() {
  local reason="$1"
  local bad_file="${OUT_FILE}.bad.mkv"

  echo "[record] Marking recording bad: ${reason}" | tee -a "${LOG_FILE}"

  if [[ -f "${TMP_FILE}" ]]; then
    mv "${TMP_FILE}" "${bad_file}" || true
  fi

  exit 1
}

###############################################################################
# Preflight checks
###############################################################################

if [[ ! -e "${VAAPI_DEV}" ]]; then
  echo "[record] ERROR: VAAPI device missing: ${VAAPI_DEV}" | tee -a "${LOG_FILE}"
  exit 1
fi

if [[ ! -e "${VIDEO_DEV}" ]]; then
  echo "[record] ERROR: Video device missing: ${VIDEO_DEV}" | tee -a "${LOG_FILE}"
  exit 1
fi

if ! pactl list short sources | grep -q "${AUDIO_SRC}"; then
  echo "[record] ERROR: Pulse source not found: ${AUDIO_SRC}" | tee -a "${LOG_FILE}"
  exit 1
fi

###############################################################################
# Run ffmpeg (background, supervised)
###############################################################################

ffmpeg -hide_banner -loglevel info \
  -init_hw_device vaapi=va:"${VAAPI_DEV}" -filter_hw_device va \
  -fflags +genpts \
  -f v4l2 -input_format mjpeg -framerate 30 -video_size 1920x1080 -i "${VIDEO_DEV}" \
  -f pulse -i "${AUDIO_SRC}" \
  -vf "hflip,format=nv12,hwupload" -c:v hevc_vaapi -qp 24 \
  -c:a flac -compression_level 1 -ar 48000 -ac 1 \
  -f matroska \
  "${TMP_FILE}" >> "${LOG_FILE}" 2>&1 &

FF_PID=$!

###############################################################################
# Wait safely (protect against set -e)
###############################################################################

set +e
wait "${FF_PID}"
FF_EXIT=$?
set -e

###############################################################################
# Validate ffmpeg exit
###############################################################################

if [[ ${FF_EXIT} -ne 0 && ${FF_EXIT} -ne 130 && ${FF_EXIT} -ne 255 ]]; then
  finalize_bad "ffmpeg exit ${FF_EXIT}"
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
    -select_streams v:0 \
    -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 \
    "${TMP_FILE}" 2>/dev/null || true
)"

if [[ "${DURATION}" == "N/A" || -z "${DURATION}" ]]; then
  echo "[record] Duration unavailable, accepting based on container integrity" | tee -a "${LOG_FILE}"
else
  if awk "BEGIN {exit !(${DURATION} > 0.5)}"; then
    :
  else
    finalize_bad "too short ${DURATION}"
  fi
fi

###############################################################################
# Atomic finalize (good path)
###############################################################################

mv "${TMP_FILE}" "${OUT_FILE}"

echo "[record] Capture complete → ${OUT_FILE}" | tee -a "${LOG_FILE}"
echo "[record] Duration: ${DURATION}s" | tee -a "${LOG_FILE}"

exit 0
