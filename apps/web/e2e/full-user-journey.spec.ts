import { expect, test, type Page } from "@playwright/test";

const leafLabels = [
  "机构及产品",
  "机构及产品指标",
  "机构及产品数据录入",
  "机构及产品预测输出",
  "预算展示报表",
  "模拟测算（正算）",
  "模拟测算（倒算）",
  "部门科目维护",
  "部门预算科目维护",
  "BI映射维护",
  "预算录入",
  "费用执行明细导入",
  "费用预测逻辑配置",
  "部门费用预测",
  "费用预算执行报表",
  "业务支出成本收入比实际导入",
  "业务支出成本收入比维护",
  "投入产出专题概览",
  "当前可编辑年度多版本透视报表",
  "多年度对比透视报表",
  "多年度数据透视图",
  "智能分析报告",
  "智能演示PPT",
  "用户和权限管理",
  "系统设定控制",
  "数据同步管理",
  "预算事实刷新跑批",
  "Agent对话测试",
  "使用说明",
  "常见问题",
  "联系管理员",
];

const retiredLeafLabels = [
  "数据科目运行表",
  "产品科目维护",
];

test("opens every visible leaf navigation page without runtime errors", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");
  await page.waitForLoadState("networkidle");

  const userNameInput = page.getByPlaceholder("用户名");
  if (await userNameInput.isVisible().catch(() => false)) {
    await userNameInput.fill(process.env.E2E_USER || "Arthur");
    await page.getByPlaceholder("密码").fill(process.env.E2E_PASSWORD || "Arthur2026");
    await page.getByRole("button", { name: "登录" }).click();
  }

  const tree = page.locator(".bb-tree-pane");
  await expect(tree).toBeVisible();

  for (const label of retiredLeafLabels) {
    await expect(tree.getByText(label, { exact: true }), `${label} should stay retired`).toHaveCount(0);
  }

  for (const label of leafLabels) {
    await closeBlockingDialogs(page);
    const item = tree.getByText(label, { exact: true });
    await expect(item, `${label} should be visible in navigation`).toBeVisible();
    await item.click();
    await page.waitForTimeout(350);
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/Internal Server Error|TypeError|ReferenceError|Unhandled|Cannot read/);
    expect(pageErrors, `runtime errors after opening ${label}`).toEqual([]);
  }
  await closeBlockingDialogs(page);
});

async function closeBlockingDialogs(page: Page) {
  const closeButtons = page.getByRole("button", { name: "关闭" });
  while ((await closeButtons.count()) > 0 && (await closeButtons.first().isVisible().catch(() => false))) {
    await closeButtons.first().click();
    await page.waitForTimeout(100);
  }
  await page.keyboard.press("Escape").catch(() => undefined);
}
