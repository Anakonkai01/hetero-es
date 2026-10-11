import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { AppProviders } from "./app/providers";

import { AppRouter } from "./app/router";
import "./index.css";
import { IS_MOCK } from "./lib/dataSource";
import {ProductProvider} from '@heteroes/product-ui';
import '@heteroes/product-ui/theme.css';
import './product.css';

async function enableMocking() {
  if (!IS_MOCK) {
    if ("serviceWorker" in navigator) {
      for (const registration of await navigator.serviceWorker.getRegistrations()) {
        if (registration.active?.scriptURL.endsWith("/mockServiceWorker.js")) await registration.unregister();
      }
    }
    return;
  }

  const { worker } = await import("./mocks/browser");

  await worker.start({
    onUnhandledRequest: "bypass",
  });
}

enableMocking().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ProductProvider><AppProviders>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </AppProviders></ProductProvider>
    </StrictMode>,
  );
});
