import path from "node:path";

export function resolveInside(root: string, candidate: string): string | null {
  if (!candidate || path.isAbsolute(candidate)) {
    return null;
  }

  const resolvedRoot = path.resolve(root);
  const resolvedCandidate = path.resolve(resolvedRoot, candidate);
  const relative = path.relative(resolvedRoot, resolvedCandidate);
  if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    return resolvedCandidate;
  }
  return null;
}

export function resolveTranscriptPath(
  vlogDir: string,
  transcriptDir: string,
  transcriptFile: string | null | undefined,
): string | null {
  if (!transcriptFile) {
    return null;
  }
  const resolved = resolveInside(vlogDir, transcriptFile);
  if (!resolved) {
    return null;
  }
  const relative = path.relative(path.resolve(transcriptDir), resolved);
  if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    return resolved;
  }
  return null;
}
