import { expect, test } from "@playwright/test";
import path from "node:path";

test("register, index from Data Hub, ask, and see cited company data", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(`owner-${Date.now()}@example.com`);
  await page.getByRole("button", { name: "Send code" }).click();
  const codeText = await page.getByText(/Local code:/).textContent();
  const code = codeText?.match(/\d{6}/)?.[0];
  expect(code).toBeTruthy();
  await page.getByLabel("Six-digit code").fill(code!);
  await page.getByRole("button", { name: "Verify and continue" }).click();

  await page.getByLabel("Company name").fill("Acme Knowledge");
  await page.getByRole("button", { name: "Continue to Data Hub" }).click();
  await expect(page.getByText("Data Hub")).toBeVisible();

  const sample = path.resolve(__dirname, "../sample-data/employee-handbook.md");
  await page.setInputFiles("input[type=file]", sample);
  await page.getByRole("button", { name: "Upload and index" }).click();
  await expect(page.getByText(/Uploaded 1 file/)).toBeVisible({ timeout: 30_000 });

  await page.goto("/activity");
  await expect(page.getByText(/COMPLETED|COMPLETED WITH WARNINGS/).first()).toBeVisible({ timeout: 90_000 });

  await page.goto("/ask");
  await page.getByRole("button", { name: "Company data" }).click();
  await page.getByPlaceholder("Ask about policy, projects, customers, systems, or live tools").fill("What is the leave policy?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/annual leave|leave policy/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/\[1\]/)).toBeVisible();
});

test("fresh workspace shows unavailable live modes before sources are connected", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(`empty-${Date.now()}@example.com`);
  await page.getByRole("button", { name: "Send code" }).click();
  const codeText = await page.getByText(/Local code:/).textContent();
  const code = codeText?.match(/\d{6}/)?.[0];
  expect(code).toBeTruthy();
  await page.getByLabel("Six-digit code").fill(code!);
  await page.getByRole("button", { name: "Verify and continue" }).click();

  await page.getByLabel("Company name").fill("Empty Knowledge");
  await page.getByRole("button", { name: "Continue to Data Hub" }).click();
  await page.goto("/ask");

  await expect(page.getByRole("button", { name: "Company data" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Live web" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "MCP tools" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Blended" })).toBeDisabled();
});
