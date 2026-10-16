import {
  AlertTriangle,
  BatteryFull,
  BatteryLow,
  BatteryMedium,
  Bed,
  Cloud,
  Coffee,
  Eye,
  Frown,
  Gauge,
  Laugh,
  Meh,
  Moon,
  Scale,
  Smile,
  Zap,
  ZapOff,
  type LucideIcon,
} from "lucide-react";
import { numberOrDash } from "../formatters";
import type { Recording } from "../types";

function iconFor(value: number | null | undefined, choices: Array<[number, LucideIcon]>, fallback: LucideIcon) {
  if (value === null || value === undefined) return fallback;
  for (const [max, Icon] of choices) {
    if (value <= max) return Icon;
  }
  return fallback;
}

function moodIcon(value: number | null | undefined) {
  return iconFor(value, [[1, Frown], [2, Meh], [4, Smile]], Laugh);
}

function energyIcon(value: number | null | undefined) {
  return iconFor(value, [[1, ZapOff], [2, BatteryLow], [3, BatteryMedium], [4, BatteryFull]], Zap);
}

function stressIcon(value: number | null | undefined) {
  return iconFor(value, [[4, Gauge]], AlertTriangle);
}

function sleepinessIcon(value: number | null | undefined) {
  return iconFor(value, [[1, Eye], [2, Cloud], [4, Moon]], Bed);
}

function LifeChip({
  className,
  icon: Icon,
  label,
  value,
}: {
  className: string;
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <span className={`life-chip ${className}`}>
      <Icon size={14} />
      {label} {value}
    </span>
  );
}

export function LifeMetadata({ life }: { life: Recording["life"] }) {
  return (
    <section className="inspector-block" data-testid="life-metadata-block">
      <h3>Life metadata</h3>
      <div className="life-grid">
        <div className="life-grid-row life-grid-row-primary">
          <LifeChip className="mood" icon={moodIcon(life.mood)} label="mood" value={numberOrDash(life.mood)} />
          <LifeChip
            className="energy"
            icon={energyIcon(life.energy)}
            label="energy"
            value={numberOrDash(life.energy)}
          />
          <LifeChip
            className="stress"
            icon={stressIcon(life.stress)}
            label="stress"
            value={numberOrDash(life.stress)}
          />
          <LifeChip
            className="sleepiness"
            icon={sleepinessIcon(life.sleepiness)}
            label="sleepy"
            value={numberOrDash(life.sleepiness)}
          />
        </div>
        <div className="life-grid-row life-grid-row-secondary">
          <LifeChip
            className="sleep-hours"
            icon={Bed}
            label="sleep hrs"
            value={numberOrDash(life.sleepHours, "h")}
          />
          {life.caffeineMg !== null ? (
            <LifeChip className="caffeine" icon={Coffee} label="caffeine" value={numberOrDash(life.caffeineMg, "mg")} />
          ) : null}
          {life.bodyWeight !== null ? (
            <LifeChip className="body-weight" icon={Scale} label="weight" value={numberOrDash(life.bodyWeight)} />
          ) : null}
        </div>
      </div>
    </section>
  );
}
