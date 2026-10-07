export function hasTableMaterial(files: readonly { name: string }[], refs: readonly string[]): boolean {
  return [...files.map(file => file.name), ...refs].some(name => /\.(csv|xlsx)$/i.test(name));
}

// Material inference is derived from the current attachments, never stored as a sticky skill.
export function composerSkill(files: readonly { name: string }[], refs: readonly string[], selected?: string, detected?: string): string | undefined {
  return hasTableMaterial(files, refs) ? "table_analysis" : selected || detected || undefined;
}

export function runStatusLabel(status: string): string {
  return ({ success: "成功", failed: "失败", paused: "已暂停", interrupted: "已中断", running: "执行中" } as Record<string, string>)[status] || status;
}
