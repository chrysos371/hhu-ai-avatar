import { expect, test, type Page } from "@playwright/test";
const token = "mission-control-disposable-e2e-token";
test.beforeEach(async ({ page }) => {
  await page.goto("/chat#" + token);
  await expect(page.getByRole("heading", { name: "对话观测", exact: true })).toBeVisible();
});
async function chat(page: Page) {
  await page.getByLabel("消息", { exact: true }).fill("你好");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.locator(".chat-message.assistant")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "朗读回复" })).toBeVisible();
}
test("playback follows the audio clock, pause and stop close the mouth", async ({ page }) => {
  await chat(page);
  const response = page.waitForResponse(r => r.url().includes("/speech/audio/"));
  await page.getByRole("button", { name: "朗读回复" }).click();
  const audioResponse = await response;
  expect(audioResponse.ok()).toBe(true);
  expect(audioResponse.url()).not.toContain(token);
  expect(audioResponse.request().headers()["x-avatar-token"]).toBe(token);
  const player = page.getByLabel(/语音播放器$/);
  await expect(player).toBeVisible();
  await expect.poll(() => player.evaluate((element: HTMLAudioElement) => element.currentTime)).toBeGreaterThan(0.05);
  await expect.poll(async () => Number(await page.locator(".avatar-stage").getAttribute("data-mouth-open"))).toBeGreaterThan(0);
  await player.evaluate((audio: HTMLAudioElement) => audio.pause());
  await expect(page.locator(".avatar-stage")).toHaveAttribute("data-mouth-open", "0.000");
  await player.evaluate((audio: HTMLAudioElement) => { audio.currentTime = 0.1; return audio.play(); });
  await expect(page.locator(".avatar-stage")).toHaveAttribute("aria-label", /，正在说话$/);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../data/speech-demo/browser-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "停止播放", exact: true }).click();
  await expect(player).not.toHaveAttribute("src");
  await expect(page.locator(".avatar-stage")).toHaveAttribute("data-mouth-open", "0.000");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../data/speech-demo/browser-mobile.png", fullPage: true });
});
test("speech failure keeps the text and permits retry", async ({ page }) => {
  await chat(page);
  const text = await page.locator(".chat-message.assistant > div").first().textContent();
  await page.route("**/api/v1/speech", route => route.fulfill({ status: 503,
    contentType: "application/json", body: JSON.stringify({ data: null,
      error: { code: "speech_unavailable", message: "测试语音服务暂不可用" } }) }));
  await page.getByRole("button", { name: "朗读回复" }).click();
  await expect(page.getByRole("alert")).toContainText("测试语音服务暂不可用");
  await expect(page.locator(".chat-message.assistant > div").first()).toHaveText(text!);
  await page.unroute("**/api/v1/speech");
  await page.getByRole("button", { name: "朗读回复" }).click();
  await expect(page.getByLabel(/语音播放器$/)).toBeVisible();
});
test("WAV and microphone transcription fill a draft without sending it", async ({ page, context }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await context.grantPermissions(["microphone"]);
  await expect(page.getByLabel("上传 WAV 语音")).toBeEnabled();
  const wav = Buffer.alloc(44 + 3200);
  wav.write("RIFF", 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(16000, 24); wav.writeUInt32LE(32000, 28); wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34); wav.write("data", 36); wav.writeUInt32LE(3200, 40);
  await page.getByLabel("上传 WAV 语音").setInputFiles({ name: "voice.wav", mimeType: "audio/wav", buffer: wav });
  await expect(page.getByLabel("消息", { exact: true })).toHaveValue("浏览器识别草稿");
  await page.getByRole("button", { name: "麦克风输入" }).click();
  await expect(page.getByText("正在录音，最长 60 秒…")).toBeVisible();
  await expect(page.getByRole("button", { name: "发送消息" })).toBeDisabled();
  // Accumulate several real AudioWorklet buffers from Chromium's synthetic microphone.
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "结束并识别" }).click();
  await expect(page.getByLabel("消息", { exact: true })).toHaveValue("浏览器识别草稿\n浏览器识别草稿");
  await expect(page.locator(".chat-message")).toHaveCount(0);
  expect(errors).toEqual([]);
});
test("leaving chat releases audio playback", async ({ page }) => {
  await chat(page);
  await page.getByRole("button", { name: "朗读回复" }).click();
  const player = page.getByLabel(/语音播放器$/);
  await expect.poll(() => player.evaluate((audio: HTMLAudioElement) => audio.currentTime)).toBeGreaterThan(0.05);
  const audio = await player.elementHandle();
  await page.getByRole("link", { name: "总览", exact: true }).click();
  expect(await audio!.evaluate((element: HTMLAudioElement) => element.paused && !element.hasAttribute("src"))).toBe(true);
});
