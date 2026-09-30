/** 按技能推荐的报告下载形态（第 1.5 阶段） */
export type ExportKind = "md" | "docx" | "xlsx" | "pptx";

const WORD_SKILLS = new Set([
  "weekly_report",
  "meeting_minutes",
  "email_draft",
  "proposal_template",
  "customer_reply",
  "project_update",
  "speech_script",
  "event_retro",
  "internal_notice",
  "meeting_prep",
]);

const EXCEL_SKILLS = new Set(["table_analysis"]);

const MARKDOWN_SKILLS = new Set([
  "competitor_research",
  "industry_brief",
  "policy_brief",
]);

export function recommendedExport(skillId?: string | null): ExportKind {
  const id = (skillId || "").trim();
  if (EXCEL_SKILLS.has(id)) return "xlsx";
  if (WORD_SKILLS.has(id)) return "docx";
  if (MARKDOWN_SKILLS.has(id)) return "md";
  return "md";
}

export function exportLabel(kind: ExportKind): string {
  switch (kind) {
    case "md":
      return "Markdown";
    case "docx":
      return "Word";
    case "xlsx":
      return "Excel";
    case "pptx":
      return "PPT";
  }
}
