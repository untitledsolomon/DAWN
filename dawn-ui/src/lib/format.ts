/** Compact relative timestamp, matching the preview's mono style ("4m", "1h", "2d"). */
export function timeAgo(dateStr: string | number | Date): string {
  const date = new Date(dateStr);
  const mins = Math.floor((Date.now() - date.getTime()) / 1000 / 60);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  return `${Math.floor(days / 30)}mo`;
}
