import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
// JSDOM's MessageEvent and Node's native BroadcastChannel are different realms.
// Cross-tab transport is exercised by Chromium; unit tests use local events.
beforeEach(() => vi.stubGlobal('BroadcastChannel', undefined));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
