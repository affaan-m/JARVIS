import { test, expect } from "@playwright/test";

test.describe("SPECTER Smoke Test", () => {
  test("renders corkboard with person cards, opens and closes dossier, and shows live feed", async ({ page }) => {
    await page.goto("/");

    // 1. Verify the app shell renders
    await expect(page.getByTestId("specter-app")).toBeVisible();

    // 2. Verify the Corkboard container renders
    await expect(page.getByTestId("corkboard-container")).toBeVisible();

    // 3. Verify at least one person card renders (demo data has 3)
    const firstCard = page.getByTestId("person-card-person_1");
    await expect(firstCard).toBeVisible({ timeout: 10_000 });

    // 4. Verify multiple person cards exist
    const allCards = page.locator("[data-person-card]");
    await expect(allCards).toHaveCount(3);

    // 5. Dossier should already be open (page.tsx defaults to first person selected)
    const dossier = page.getByTestId("dossier-view");
    await expect(dossier).toBeVisible();

    // 6. Verify dossier shows the person's name
    await expect(dossier.getByText("Jordan Vale")).toBeVisible();

    // 7. Close the dossier
    await page.getByTestId("close-dossier").click();
    await expect(dossier).not.toBeVisible();

    // 8. Click a different person card to reopen dossier
    await page.getByTestId("person-card-person_2").click();
    await expect(page.getByTestId("dossier-view")).toBeVisible();
    await expect(page.getByTestId("dossier-view").getByText("Mina Sol")).toBeVisible();

    // 9. Verify LiveFeed section exists
    const liveFeed = page.getByTestId("live-feed");
    await expect(liveFeed).toBeVisible();
    await expect(liveFeed.getByText("ACTIVE SIGNALS")).toBeVisible();
  });
});
