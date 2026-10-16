export class ApiError extends Error {
  field: string | null;
  fieldErrors: Record<string, string>;

  constructor(
    message: string,
    field: string | null = null,
    fieldErrors: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.field = field;
    this.fieldErrors = fieldErrors;
  }
}

export async function jsonFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    let payload: {
      error?: unknown;
      message?: unknown;
      field?: unknown;
      field_errors?: unknown;
    } = {};
    try {
      payload = (await response.json()) as {
        error?: unknown;
        message?: unknown;
        field?: unknown;
        field_errors?: unknown;
      };
    } catch {
      payload = {};
    }
    const fieldErrors =
      payload.field_errors &&
      typeof payload.field_errors === "object" &&
      !Array.isArray(payload.field_errors)
        ? Object.fromEntries(
            Object.entries(payload.field_errors).filter(
              (entry): entry is [string, string] => typeof entry[1] === "string",
            ),
          )
        : {};
    throw new ApiError(
      typeof payload.message === "string"
        ? payload.message
        : typeof payload.error === "string"
          ? payload.error
          : `${response.status} ${response.statusText}`,
      typeof payload.field === "string" ? payload.field : null,
      fieldErrors,
    );
  }
  return (await response.json()) as T;
}
