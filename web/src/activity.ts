/**
 * Human names for what config.yaml stores as UPV codes.
 *
 * The config keeps the activity as UPV writes it ("MUSCULACION", campus "V"),
 * which is what the booking URLs need; the UI shows the readable form.
 */

const ACTIVITY_NAMES: Record<string, string> = {
  MUSCULACION: "Musculación",
};

const CAMPUS_NAMES: Record<string, string> = {
  V: "Vera",
  G: "Gandia",
  A: "Alcoy",
};

function titleCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

export function describeActivity(activity: { name: string; campus: string }): string {
  const name = ACTIVITY_NAMES[activity.name] ?? titleCase(activity.name);
  const campus = CAMPUS_NAMES[activity.campus] ?? activity.campus;
  return `${name} · Campus ${campus}`;
}
