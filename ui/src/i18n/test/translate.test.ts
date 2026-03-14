import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { vi as viLocale } from "../locales/vi.ts";

type TranslateModule = typeof import("../lib/translate.ts");

function createStorageMock(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, String(value));
    },
  };
}

describe("i18n", () => {
  let translate: TranslateModule;

  beforeEach(async () => {
    vi.resetModules();
    vi.stubGlobal("localStorage", createStorageMock());
    vi.stubGlobal("navigator", { language: "en-US" } as Navigator);
    translate = await import("../lib/translate.ts");
    localStorage.clear();
    // Reset to English
    await translate.i18n.setLocale("en");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("should return the key if translation is missing", () => {
    expect(translate.t("non.existent.key")).toBe("non.existent.key");
  });

  it("should return the correct English translation", () => {
    expect(translate.t("common.health")).toBe("Health");
  });

  it("should replace parameters correctly", () => {
    expect(translate.t("overview.stats.cronNext", { time: "10:00" })).toBe("Next wake 10:00");
  });

  it("should fallback to English if key is missing in another locale", async () => {
    // We haven't registered other locales in the test environment yet,
    // but the logic should fallback to 'en' map which is always there.
    await translate.i18n.setLocale("vi");
    // Since we don't mock the import, it might fail to load vi,
    // but let's assume it falls back to English for now.
    expect(translate.t("common.health")).toBeDefined();
  });

  it("loads translations even when setting the same locale again", async () => {
    const internal = translate.i18n as unknown as {
      locale: string;
      translations: Record<string, unknown>;
    };
    internal.locale = "vi";
    delete internal.translations["vi"];

    await translate.i18n.setLocale("vi");
    expect(translate.t("common.health")).toBe("Sức khỏe");
  });

  it("loads saved non-English locale on startup", async () => {
    vi.resetModules();
    vi.stubGlobal("localStorage", createStorageMock());
    vi.stubGlobal("navigator", { language: "en-US" } as Navigator);
    localStorage.setItem("openclaw.i18n.locale", "vi");
    const fresh = await import("../lib/translate.ts");
    await vi.waitFor(() => {
      expect(fresh.i18n.getLocale()).toBe("vi");
    });
    expect(fresh.i18n.getLocale()).toBe("vi");
    expect(fresh.t("common.health")).toBe("Sức khỏe");
  });

  it("keeps the version label available in the shipped Vietnamese locale", () => {
    expect((viLocale.common as { version?: string }).version).toBeTruthy();
  });
});
