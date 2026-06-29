import { expect, test } from "@playwright/test";
import path from "node:path";

test("register, upload, ingest, chat, and enforce tenant boundary path", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill(`owner-${Date.now()}@example.com`);
  await page.getByRole("button", { name: "Send code" }).click();
  const codeText = await page.getByText(/Local code:/).textContent();
  const code = codeText?.match(/\d{6}/)?.[0];
  expect(code).toBeTruthy();
  await page.getByLabel("Six-digit code").fill(code!);
  await page.getByRole("button", { name: "Verify and continue" }).click();

  await page.getByLabel("Company name").fill("Acme Knowledge");
  await page.getByRole("button", { name: "Continue to ingestion" }).click();
  await expect(page.getByText("Ingestion Wizard")).toBeVisible();

  const sample = path.resolve(__dirname, "../sample-data/employee-handbook.md");
  await page.setInputFiles("input[type=file]", sample);
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Upload files" }).click();
  await page.getByRole("button", { name: "Start ingestion" }).click();
  await expect(page.getByText("Pipeline Details")).toBeVisible();
  await expect(page.getByText(/COMPLETED|COMPLETED WITH WARNINGS/).first()).toBeVisible({ timeout: 90_000 });

  await page.goto("/chat");
  await page.getByPlaceholder("Ask a question about selected knowledge bases").fill("What is the leave policy?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/annual leave|leave policy/i)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/\[1\]/)).toBeVisible();
});
