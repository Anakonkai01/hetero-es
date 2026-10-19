import { ProductProvider } from '@heteroes/product-ui';
import '@heteroes/product-ui/theme.css';
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { AppProviders } from "./app/providers";
import { AppRouter } from "./app/router";
import "./index.css";
import './product.css';
  createRoot(document.getElementById("root")!).render(<StrictMode>
      <ProductProvider><AppProviders>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </AppProviders></ProductProvider>
    </StrictMode>);
