import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// Next.js navigation mocks
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}));

// JSDOM doesn't ship crypto.randomUUID in every environment
if (!globalThis.crypto?.randomUUID) {
  (globalThis as unknown as { crypto: Crypto }).crypto = {
    ...(globalThis.crypto ?? {}),
    randomUUID: () => `00000000-0000-4000-8000-${Math.random().toString(16).slice(2, 14).padEnd(12, "0")}` as `${string}-${string}-${string}-${string}-${string}`,
  } as Crypto;
}

// ResizeObserver stub for Recharts
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver = ResizeObserverStub;
