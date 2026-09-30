/** 自动化站内结果通知：localStorage 已读水位（刷新后仍可知未读失败）。 */

import type { ScheduleNotice } from "./api";

const ACK_KEY = "ai_office_sched_acked_runs";
const ACK_CAP = 200;

export function loadAckedRunIds(): Set<string> {
  try {
    const raw = window.localStorage.getItem(ACK_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.filter((x) => typeof x === "string"));
  } catch {
    return new Set();
  }
}

export function saveAckedRunIds(ids: Set<string>): void {
  try {
    const list = Array.from(ids).slice(-ACK_CAP);
    window.localStorage.setItem(ACK_KEY, JSON.stringify(list));
  } catch {
    /* ignore quota / private mode */
  }
}

export function ackRunIds(runIds: string[]): Set<string> {
  const next = loadAckedRunIds();
  for (const id of runIds) {
    if (id) next.add(id);
  }
  saveAckedRunIds(next);
  return next;
}

export function unreadNotices(
  notices: ScheduleNotice[],
  acked: Set<string> = loadAckedRunIds()
): ScheduleNotice[] {
  return notices.filter((n) => n.run_id && !acked.has(n.run_id));
}

export function unreadFailures(notices: ScheduleNotice[], acked?: Set<string>): ScheduleNotice[] {
  return unreadNotices(notices, acked).filter((n) => n.status === "failed");
}

export function formatNoticeLine(n: ScheduleNotice): string {
  const name = n.schedule_name || "自动化";
  if (n.status === "failed") {
    const brief = (n.error || "执行失败").replace(/\s+/g, " ").slice(0, 80);
    return `「${name}」失败：${brief}`;
  }
  return `「${name}」已跑完`;
}
