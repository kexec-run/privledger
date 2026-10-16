export function localTime(value: string | null) {
  if (!value) return "--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(11, 16);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function compactDate(date: string) {
  const parsed = new Date(`${date}T00:00:00`);
  return parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function numberOrDash(value: number | null, suffix = "") {
  return value === null || value === undefined ? "—" : `${value}${suffix}`;
}

export function durationLabel(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "Length unavailable";
  const totalSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = `${totalSeconds % 60}`.padStart(2, "0");
  return `${minutes}:${remainingSeconds}`;
}

export function timerLabel(startedAt: string | null | undefined, now: number) {
  if (!startedAt) return "00:00";
  const started = Date.parse(startedAt);
  if (Number.isNaN(started)) return "00:00";
  const elapsedSeconds = Math.max(0, Math.floor((now - started) / 1000));
  const hours = Math.floor(elapsedSeconds / 3600);
  const minutes = Math.floor((elapsedSeconds % 3600) / 60);
  const seconds = `${elapsedSeconds % 60}`.padStart(2, "0");
  if (hours > 0) {
    return `${hours}:${`${minutes}`.padStart(2, "0")}:${seconds}`;
  }
  return `${minutes}:${seconds}`;
}

export function formatLocalDate(date: Date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}
