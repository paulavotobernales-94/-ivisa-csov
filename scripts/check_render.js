// check_render.js — headless render guard for the CSOV report.
//
// Loads the generated report in a real (headless) browser and confirms the page
// actually populates — i.e. the JavaScript ran without a fatal error. This is the
// only check that catches RUNTIME JS errors (node --check only catches syntax).
// It is what would have caught the "stuck on Loading… / score shows --" breakage.
//
//   node scripts/check_render.js docs/index.html
//
// Exit 0 = page rendered (heroScore populated, weekRange no longer "Loading...",
//          no uncaught page error). Exit 1 = broken (CI must NOT publish).
//
// Run in CI after report generation, before commit/deploy. Requires `puppeteer`.

const path = require("path");

(async () => {
  const file = process.argv[2];
  if (!file) { console.error("usage: node check_render.js <html-file>"); process.exit(2); }

  let puppeteer;
  try { puppeteer = require("puppeteer"); }
  catch (e) { console.error("puppeteer not installed: " + e.message); process.exit(2); }

  const url = "file://" + path.resolve(file);
  const pageErrors = [];
  let browser;
  try {
    browser = await puppeteer.launch({ args: ["--no-sandbox", "--disable-setuid-sandbox"] });
    const page = await browser.newPage();
    // Uncaught JS exceptions (the real signal that the script broke).
    page.on("pageerror", (err) => pageErrors.push(err.message));
    await page.goto(url, { waitUntil: "networkidle2", timeout: 45000 });
    await new Promise((r) => setTimeout(r, 1500)); // let on-load JS settle

    const hero = await page.$eval("#heroScore", (el) => el.textContent.trim()).catch(() => null);
    const week = await page.$eval("#weekRange", (el) => el.textContent.trim()).catch(() => null);
    await browser.close();

    const heroOk = !!hero && hero !== "--" && /^[0-9]+(\.[0-9]+)?$/.test(hero);
    const weekOk = !!week && week.toLowerCase() !== "loading...";

    if (!heroOk || !weekOk || pageErrors.length) {
      console.error("RENDER CHECK FAILED — the page did not populate (would hang on 'Loading…'):");
      console.error("  heroScore=" + JSON.stringify(hero) + "  weekRange=" + JSON.stringify(week));
      pageErrors.forEach((e) => console.error("  JS error: " + e));
      process.exit(1);
    }
    console.log("RENDER OK — heroScore=" + hero + ", weekRange=" + JSON.stringify(week) + ", no JS errors.");
    process.exit(0);
  } catch (e) {
    if (browser) { try { await browser.close(); } catch (_) {} }
    console.error("RENDER CHECK could not complete: " + e.message);
    process.exit(1); // conservative: if we couldn't verify the page, don't publish
  }
})();
