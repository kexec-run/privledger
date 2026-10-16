import {
  type EnrichmentDescription,
  type EnrichmentForm as EnrichmentValues,
} from "../types";

export type EnrichmentMetricField = {
  key: "mood" | "energy" | "stress" | "sleepiness" | "sleep_hours" | "caffeine_mg" | "body_weight";
  label: string;
  min?: number;
  max?: number;
  step?: number;
};

export const ENRICHMENT_METRIC_FIELDS: EnrichmentMetricField[] = [
  { key: "mood", label: "Mood", min: 1, max: 5 },
  { key: "energy", label: "Energy", min: 1, max: 5 },
  { key: "stress", label: "Stress", min: 1, max: 5 },
  { key: "sleepiness", label: "Sleepiness", min: 1, max: 5 },
  { key: "sleep_hours", label: "Sleep hours", min: 0, step: 0.25 },
  { key: "caffeine_mg", label: "Caffeine mg", min: 0 },
  { key: "body_weight", label: "Body weight", min: 0, step: 0.1 },
];

type Props = {
  description: EnrichmentDescription | null;
  values: EnrichmentValues | null;
  tags: string[];
  fields: EnrichmentMetricField[];
  errors: Record<string, string>;
  error: string | null;
  busy: boolean;
  closeLabel: string;
  onClose: () => void;
  onValueChange: <K extends keyof EnrichmentDescription["values"]>(
    key: K,
    value: EnrichmentDescription["values"][K],
  ) => void;
  onCustomChange: (name: string, value: string | number | boolean | null) => void;
  onToggleTag: (tag: string) => void;
  onSubmit: () => void;
};

export function EnrichmentForm({
  description,
  values,
  tags,
  fields,
  errors,
  error,
  busy,
  closeLabel,
  onClose,
  onValueChange,
  onCustomChange,
  onToggleTag,
  onSubmit,
}: Props) {
  const vocabulary = description?.tag_vocabulary ?? tags;

  return (
    <div className="enrichment-form" data-testid="enrichment-form">
      {values ? (
        <>
          {error ? <div className="enrichment-error">{error}</div> : null}
          <div className="field-grid">
            {fields.map((field) => (
              <label
                key={field.key}
                className={errors[field.key] ? "invalid-field" : ""}
                data-testid={`enrichment-field-${field.key}`}
              >
                <span>{field.label}</span>
                <input
                  data-testid={`enrichment-input-${field.key}`}
                  type="number"
                  min={field.min}
                  max={field.max}
                  step={field.step ?? 1}
                  value={values[field.key] ?? ""}
                  onChange={(event) =>
                    onValueChange(
                      field.key,
                      event.currentTarget.value === "" ? null : Number(event.currentTarget.value),
                    )
                  }
                />
                {errors[field.key] ? <small>{errors[field.key]}</small> : null}
              </label>
            ))}
          </div>

          <label
            className={`wide-field ${errors.focus_domain ? "invalid-field" : ""}`}
            data-testid="enrichment-field-focus_domain"
          >
            <span>Focus domain</span>
            <select
              data-testid="enrichment-input-focus_domain"
              value={values.focus_domain ?? ""}
              onChange={(event) => onValueChange("focus_domain", event.currentTarget.value || null)}
            >
              <option value="">None</option>
              {vocabulary.map((tag) => <option key={tag} value={tag}>{tag}</option>)}
            </select>
            {errors.focus_domain ? <small>{errors.focus_domain}</small> : null}
          </label>

          <div className={`tag-picker ${errors.tags ? "invalid-field" : ""}`} data-testid="enrichment-tags">
            {vocabulary.map((tag) => (
              <button
                key={tag}
                className={values.tags.includes(tag) ? "active" : ""}
                onClick={() => onToggleTag(tag)}
                type="button"
              >
                {tag}
              </button>
            ))}
            {errors.tags ? <small>{errors.tags}</small> : null}
          </div>

          <label className={`wide-field ${errors.location ? "invalid-field" : ""}`} data-testid="enrichment-field-location">
            <span>Location</span>
            <input
              data-testid="enrichment-input-location"
              value={values.location ?? ""}
              onChange={(event) => onValueChange("location", event.currentTarget.value || null)}
            />
            {errors.location ? <small>{errors.location}</small> : null}
          </label>

          {description?.custom.enabled ? (
            <div className="custom-fields">
              <h4>Custom</h4>
              {description.custom.fields.map((field) => (
                <label key={field.name} className={errors.custom ? "invalid-field" : ""}>
                  <span>{field.name}</span>
                  {field.type === "boolean" ? (
                    <input
                      type="checkbox"
                      checked={Boolean(values.custom[field.name])}
                      onChange={(event) => onCustomChange(field.name, event.currentTarget.checked)}
                    />
                  ) : (
                    <input
                      type={field.type === "integer" || field.type === "number" ? "number" : "text"}
                      step={field.type === "number" ? 0.1 : 1}
                      value={String(values.custom[field.name] ?? "")}
                      onChange={(event) =>
                        onCustomChange(
                          field.name,
                          event.currentTarget.value === ""
                            ? null
                            : field.type === "integer" || field.type === "number"
                              ? Number(event.currentTarget.value)
                              : event.currentTarget.value,
                        )
                      }
                    />
                  )}
                  {errors.custom ? <small>{errors.custom}</small> : null}
                </label>
              ))}
            </div>
          ) : null}

          <div className="enrichment-actions">
            <button className="button neutral" disabled={busy} onClick={onClose}>
              {closeLabel}
            </button>
            <button
              className="button record"
              data-testid="save-enrichment-button"
              disabled={busy}
              onClick={onSubmit}
            >
              Save enrichment
            </button>
          </div>
        </>
      ) : (
        <p className="muted-copy">Loading enrichment fields…</p>
      )}
    </div>
  );
}
