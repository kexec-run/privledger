import { ChevronDown, Circle, RefreshCw, Square, X } from "lucide-react";
import type { ReactNode } from "react";
import type { RecordingGuide } from "../types";

export type RecordingSessionPhase = "prepare" | "recording" | "saving" | "enrichment";

type GuideSection = RecordingGuide["sections"][number];

type Props = {
  phase: RecordingSessionPhase;
  elapsed: string;
  busy: boolean;
  guideSource?: string;
  guideSections: RecordingGuide["sections"];
  selectedGuide: GuideSection | null;
  enrichmentForm: ReactNode;
  onCancel: () => void;
  onStart: () => void;
  onStop: () => void;
  onClose: () => void;
  onGuideSelect: (title: string) => void;
};

export function RecordingSessionDialog({
  phase,
  elapsed,
  busy,
  guideSource,
  guideSections,
  selectedGuide,
  enrichmentForm,
  onCancel,
  onStart,
  onStop,
  onClose,
  onGuideSelect,
}: Props) {
  return (
    <div className="session-overlay" role="presentation">
      <section
        className={`session-dialog ${phase}`}
        data-testid="session-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-title"
      >
        <header className="session-header">
          <div>
            <span className="session-kicker">
              <Circle size={11} fill="currentColor" />
              {phase === "enrichment" ? "Recording complete" : phase === "prepare" ? "Prepare" : "Recording"}
            </span>
            <h2 id="session-title">
              {phase === "enrichment"
                ? "Enrich metadata"
                : phase === "saving"
                  ? "Saving recording"
                  : phase === "prepare"
                    ? "Prepare recording"
                    : "Recording"}
            </h2>
          </div>
          <div className="session-controls">
            {phase === "recording" ? <strong className="session-timer">{elapsed}</strong> : null}
            {phase === "prepare" ? (
              <>
                <button className="button neutral" data-testid="cancel-recording-button" disabled={busy} onClick={onCancel}>
                  Cancel
                </button>
                <button className="button record session-stop" data-testid="start-recording-button" disabled={busy} onClick={onStart}>
                  <Circle size={15} fill="currentColor" />
                  Start recording
                </button>
              </>
            ) : null}
            {phase === "recording" ? (
              <button className="button record session-stop" data-testid="stop-recording-button" disabled={busy} onClick={onStop}>
                <Square size={15} fill="currentColor" />
                Stop recording
              </button>
            ) : null}
            {phase === "enrichment" ? (
              <button className="icon-button ghost" aria-label="Close session dialog" onClick={onClose}>
                <X size={19} />
              </button>
            ) : null}
          </div>
        </header>

        {phase === "saving" ? (
          <div className="session-saving">
            <RefreshCw size={24} />
            <div>
              <strong>Saving locally</strong>
              <span>Stopping recorder, refreshing index, and finding the new JSON.</span>
            </div>
          </div>
        ) : null}

        {phase === "prepare" || phase === "recording" ? (
          <>
            <div className="session-status-line">
              {phase === "prepare" ? (
                <>
                  <span>Recorder not started</span>
                  <span>Read prompts, then start when ready</span>
                </>
              ) : (
                <>
                  <span>Saving locally</span>
                  <span>Camera owned by Python recorder</span>
                </>
              )}
            </div>

            <section className="guide-panel">
              <div className="guide-heading">
                <div>
                  <span className="eyeless-label">{guideSource ?? "docs/questions.md"}</span>
                  <h3>questions.md guide</h3>
                </div>
                <p>Use these as prompts, not a checklist.</p>
              </div>

              {guideSections.length > 0 ? (
                <div className="guide-section-list">
                  {guideSections.slice(0, 6).map((section) => {
                    const isExpanded = section === selectedGuide;
                    return (
                      <div className={`guide-section ${isExpanded ? "expanded" : ""}`} key={section.title}>
                        <button
                          aria-expanded={isExpanded}
                          className="guide-section-title"
                          data-testid="guide-section-title"
                          data-guide-title={section.title}
                          onClick={() => onGuideSelect(isExpanded ? "" : section.title)}
                          type="button"
                        >
                          <span>{section.title}</span>
                          <small>{section.prompts.length} prompts</small>
                          <ChevronDown size={17} />
                        </button>
                        <div
                          aria-hidden={!isExpanded}
                          className={`prompt-region ${isExpanded ? "open" : ""}`}
                          data-testid="prompt-region"
                        >
                          <div className="prompt-list">
                            {section.prompts.slice(0, 5).map((prompt) => (
                              <div className="prompt-card" key={prompt}>{prompt}</div>
                            ))}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="muted-copy">No guide prompts found.</p>
              )}
            </section>

            {phase === "recording" ? (
              <div className="quick-metadata-row">
                <span>Enrichment opens after stop</span>
                <strong>mood, energy, stress, sleepiness, tags</strong>
              </div>
            ) : null}
          </>
        ) : null}

        {phase === "enrichment" ? (
          <section className="session-enrichment" data-testid="session-enrichment">
            <p className="muted-copy">
              Recording saved. Add life metadata now, or close and re-enrich from the
              inspector later.
            </p>
            {enrichmentForm}
          </section>
        ) : null}
      </section>
    </div>
  );
}
