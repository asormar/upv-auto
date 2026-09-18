const WEEKDAYS: Record<string, number> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6,
};

const DAY_NAMES = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** The next moment the booking window opens, or null if the config can't be read. */
export function nextRunAt(weekday: string, opensAt: string, now: Date = new Date()): Date | null {
  const target = WEEKDAYS[weekday.toLowerCase()];
  const [hours, minutes = 0, seconds = 0] = opensAt.split(":").map(Number);
  if (target === undefined || Number.isNaN(hours)) return null;

  const next = new Date(now);
  next.setHours(hours, minutes, seconds, 0);
  let ahead = (target - now.getDay() + 7) % 7;
  if (ahead === 0 && next <= now) ahead = 7;
  next.setDate(next.getDate() + ahead);
  return next;
}

/** "Sábado 19 sep, 10:01" */
export function formatRunDay(date: Date): string {
  const time = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  return `${DAY_NAMES[date.getDay()]} ${date.getDate()} ${MONTHS[date.getMonth()]}, ${time}`;
}

export interface Remaining {
  hours: number;
  minutes: number;
  seconds: number;
}

/** Hours are not folded into days, so it reads as one countdown: 70:45:53. */
export function splitRemaining(milliseconds: number): Remaining {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  return {
    hours: Math.floor(total / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  };
}
